import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models.narration_image import (
    NarrationImageFrame,
    NarrationImageFrameStatus,
    NarrationImageGenerationMode,
    NarrationImageSeries,
    NarrationImageSeriesStatus,
)
from app.services.client_factory import (
    build_flux2_klein_client,
    build_invokeai_client,
    build_openai_image_client,
)
from app.services.config_manager import ConfigManager
from app.utils.media import ensure_media_dir

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_series(db, series_id: str) -> NarrationImageSeries | None:
    try:
        parsed = uuid.UUID(series_id)
    except ValueError:
        return None
    return (
        db.query(NarrationImageSeries).filter(NarrationImageSeries.id == parsed).first()
    )


def _get_frame(db, frame_id: uuid.UUID) -> NarrationImageFrame | None:
    return (
        db.query(NarrationImageFrame).filter(NarrationImageFrame.id == frame_id).first()
    )


def _ordered_frames(series: NarrationImageSeries) -> list[NarrationImageFrame]:
    return sorted(series.frames, key=lambda item: (item.step_order, item.created_at))


def _resolve_reference_image_name(
    db,
    frame: NarrationImageFrame,
) -> str:
    if frame.invokeai_reference_image_name:
        return frame.invokeai_reference_image_name

    if not frame.parent_frame_id:
        raise RuntimeError("Image-to-image frame requires a parent frame or reference")

    parent = _get_frame(db, frame.parent_frame_id)
    if not parent:
        raise RuntimeError(f"Parent frame not found: {frame.parent_frame_id}")
    if not parent.invokeai_generated_image_name:
        raise RuntimeError(
            "Parent frame has no generated InvokeAI image name for image-to-image"
        )
    return parent.invokeai_generated_image_name


def _resolve_reference_image_bytes(
    db,
    frame: NarrationImageFrame,
) -> bytes:
    if not frame.parent_frame_id:
        raise RuntimeError("Image-to-image frame requires a parent frame")

    parent = _get_frame(db, frame.parent_frame_id)
    if not parent:
        raise RuntimeError(f"Parent frame not found: {frame.parent_frame_id}")
    if not parent.output_image_path:
        raise RuntimeError(
            "Parent frame has no output_image_path for image-to-image reference"
        )

    parent_path = Path(parent.output_image_path)
    if not parent_path.exists():
        raise RuntimeError(f"Parent image file missing: {parent_path}")
    return parent_path.read_bytes()


def _active_image_provider(db) -> str:
    cfg = ConfigManager(db).get_config("image_generation")
    return cfg.get("provider") or "invokeai"


def _generate_with_invokeai(db, frame: NarrationImageFrame):
    client = build_invokeai_client(db)
    if frame.mode == NarrationImageGenerationMode.TEXT_TO_IMAGE.value:
        result = asyncio.run(
            client.generate_text_to_image(
                prompt=frame.prompt,
                width=frame.width,
                height=frame.height,
                num_steps=frame.num_steps,
                cfg_scale=frame.cfg_scale,
                seed=frame.seed,
            )
        )
        frame.invokeai_reference_image_name = None
    elif frame.mode == NarrationImageGenerationMode.IMAGE_TO_IMAGE.value:
        ref_image_name = _resolve_reference_image_name(db, frame)
        frame.invokeai_reference_image_name = ref_image_name
        result = asyncio.run(
            client.generate_with_reference(
                prompt=frame.prompt,
                ref_image_name=ref_image_name,
                width=frame.width,
                height=frame.height,
                num_steps=frame.num_steps,
                cfg_scale=frame.cfg_scale,
                seed=frame.seed,
            )
        )
    else:
        raise RuntimeError(f"Unsupported frame mode: {frame.mode}")
    frame.invokeai_generated_image_name = result.image_name
    return result


def _generate_with_flux2_klein(db, frame: NarrationImageFrame):
    client = build_flux2_klein_client(db)
    if frame.mode == NarrationImageGenerationMode.TEXT_TO_IMAGE.value:
        result = asyncio.run(
            client.generate_text_to_image(
                prompt=frame.prompt,
                width=frame.width,
                height=frame.height,
                num_steps=frame.num_steps,
                cfg_scale=frame.cfg_scale,
                seed=frame.seed,
            )
        )
    elif frame.mode == NarrationImageGenerationMode.IMAGE_TO_IMAGE.value:
        ref_bytes = _resolve_reference_image_bytes(db, frame)
        result = asyncio.run(
            client.generate_with_reference_bytes(
                prompt=frame.prompt,
                reference_bytes=ref_bytes,
                width=frame.width,
                height=frame.height,
                num_steps=frame.num_steps,
                cfg_scale=frame.cfg_scale,
                seed=frame.seed,
            )
        )
    else:
        raise RuntimeError(f"Unsupported frame mode: {frame.mode}")
    frame.invokeai_reference_image_name = None
    frame.invokeai_generated_image_name = None
    return result


def _generate_with_openai_image(db, frame: NarrationImageFrame):
    client = build_openai_image_client(db)
    if frame.mode == NarrationImageGenerationMode.TEXT_TO_IMAGE.value:
        result = asyncio.run(
            client.generate_text_to_image(
                prompt=frame.prompt,
                width=frame.width,
                height=frame.height,
                seed=frame.seed,
            )
        )
    elif frame.mode == NarrationImageGenerationMode.IMAGE_TO_IMAGE.value:
        ref_bytes = _resolve_reference_image_bytes(db, frame)
        result = asyncio.run(
            client.generate_with_reference_bytes(
                prompt=frame.prompt,
                reference_bytes=ref_bytes,
                width=frame.width,
                height=frame.height,
                seed=frame.seed,
            )
        )
    else:
        raise RuntimeError(f"Unsupported frame mode: {frame.mode}")
    frame.invokeai_reference_image_name = None
    frame.invokeai_generated_image_name = None
    return result


def _generate_frame_image(
    db,
    series: NarrationImageSeries,
    frame: NarrationImageFrame,
) -> None:
    frame.status = NarrationImageFrameStatus.GENERATING.value
    frame.error_message = None
    db.commit()

    provider = _active_image_provider(db)
    if provider == "flux2_klein":
        result = _generate_with_flux2_klein(db, frame)
    elif provider == "openai_image":
        result = _generate_with_openai_image(db, frame)
    elif provider == "invokeai":
        result = _generate_with_invokeai(db, frame)
    else:
        raise RuntimeError(f"Unknown image provider: {provider}")

    output_dir = ensure_media_dir(
        settings.media_dir,
        str(series.segment.project_id),
        "narration",
        "image_series",
        str(series.segment_id),
        str(series.id),
    )
    output_path = output_dir / f"{frame.step_order:03d}_{frame.id}.png"
    output_path.write_bytes(result.image_bytes)

    frame.provider = provider
    frame.actual_seed = result.seed
    frame.output_image_path = str(output_path)
    frame.status = NarrationImageFrameStatus.COMPLETED.value
    frame.error_message = None
    db.commit()


def _mark_frame_error(db, frame_id: uuid.UUID, message: str) -> None:
    frame = _get_frame(db, frame_id)
    if not frame:
        return
    frame.status = NarrationImageFrameStatus.ERROR.value
    frame.error_message = message[:1000]
    db.commit()


@celery.task(bind=True, max_retries=0, queue="image-sequences")
def generate_narration_image_series(self, series_id: str):
    db = SessionLocal()
    try:
        series = _get_series(db, series_id)
        if not series:
            logger.error("Narration image series %s not found", series_id)
            return

        if not series.frames:
            series.status = NarrationImageSeriesStatus.ERROR.value
            series.error_message = "Series has no frames to generate"
            db.commit()
            return

        series.status = NarrationImageSeriesStatus.GENERATING.value
        series.started_at = _utc_now()
        series.error_message = None
        db.commit()

        for frame in _ordered_frames(series):
            if frame.status != NarrationImageFrameStatus.PENDING.value:
                continue
            frame_id = frame.id
            try:
                _generate_frame_image(db, series, frame)
            except Exception as exc:
                logger.exception(
                    "Failed frame generation for series %s frame %s",
                    series_id,
                    frame_id,
                )
                _mark_frame_error(db, frame_id, str(exc))
                series = _get_series(db, series_id)
                if series:
                    series.status = NarrationImageSeriesStatus.ERROR.value
                    series.error_message = str(exc)[:1000]
                    db.commit()
                return

        series = _get_series(db, series_id)
        if not series:
            return

        has_errors = any(
            frame.status == NarrationImageFrameStatus.ERROR.value
            for frame in series.frames
        )
        has_pending = any(
            frame.status == NarrationImageFrameStatus.PENDING.value
            for frame in series.frames
        )

        if has_errors:
            series.status = NarrationImageSeriesStatus.ERROR.value
            if not series.error_message:
                series.error_message = "One or more frames failed"
            db.commit()
            return
        if has_pending:
            series.status = NarrationImageSeriesStatus.DRAFT.value
            db.commit()
            return

        series.status = NarrationImageSeriesStatus.COMPLETED.value
        series.completed_at = _utc_now()
        series.error_message = None
        db.commit()
    except Exception as exc:
        logger.exception("Narration image series generation failed: %s", exc)
        db.rollback()
        series = _get_series(db, series_id)
        if series:
            series.status = NarrationImageSeriesStatus.ERROR.value
            series.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()
