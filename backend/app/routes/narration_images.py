import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.narration import NarrationSegment
from app.models.narration_image import (
    NarrationImageFrame,
    NarrationImageFrameStatus,
    NarrationImageGenerationMode,
    NarrationImageSeries,
    NarrationImageSeriesStatus,
)
from app.models.project import ProjectType
from app.schemas.narration_image import (
    NarrationImageFrameCreate,
    NarrationImageFrameRead,
    NarrationImagePromptSuggestionRequest,
    NarrationImagePromptSuggestionResponse,
    NarrationImageRegenerateRequest,
    NarrationImageSeriesAutoCreate,
    NarrationImageSeriesCreate,
    NarrationImageSeriesRead,
)
from app.services.narration_images import (
    generate_image_sequence_plan,
    suggest_image_prompts,
)
from app.tasks.narration_images import generate_narration_image_series

logger = logging.getLogger(__name__)

router = APIRouter(tags=["narration-images"])

_ACTIVE_SERIES_STATES = {
    NarrationImageSeriesStatus.QUEUED.value,
    NarrationImageSeriesStatus.GENERATING.value,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_segment_or_404(segment_id: int, db: Session) -> NarrationSegment:
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    if segment.project.project_type != ProjectType.NARRATION.value:
        raise HTTPException(
            status_code=400,
            detail="Narration image sequences require a narration project segment",
        )
    return segment


def _get_series_or_404(series_id: uuid.UUID, db: Session) -> NarrationImageSeries:
    series = (
        db.query(NarrationImageSeries)
        .filter(NarrationImageSeries.id == series_id)
        .first()
    )
    if not series:
        raise HTTPException(status_code=404, detail="Image series not found")
    if series.segment.project.project_type != ProjectType.NARRATION.value:
        raise HTTPException(
            status_code=400,
            detail="Narration image sequences require a narration project segment",
        )
    return series


def _get_series_frame_or_404(
    series_id: uuid.UUID,
    frame_id: uuid.UUID,
    db: Session,
) -> NarrationImageFrame:
    frame = (
        db.query(NarrationImageFrame)
        .filter(
            NarrationImageFrame.id == frame_id,
            NarrationImageFrame.series_id == series_id,
        )
        .first()
    )
    if not frame:
        raise HTTPException(status_code=404, detail="Image frame not found")
    return frame


def _assert_no_other_active_series(
    db: Session,
    *,
    exclude_series_id: uuid.UUID | None = None,
) -> None:
    query = db.query(NarrationImageSeries).filter(
        NarrationImageSeries.status.in_(_ACTIVE_SERIES_STATES)
    )
    if exclude_series_id:
        query = query.filter(NarrationImageSeries.id != exclude_series_id)
    active = query.order_by(NarrationImageSeries.updated_at.asc()).first()
    if active:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Image series generation already in progress "
                f"(series_id={active.id})."
            ),
        )


def _series_read(series: NarrationImageSeries) -> NarrationImageSeriesRead:
    return NarrationImageSeriesRead.model_validate(series)


def _frame_read(frame: NarrationImageFrame) -> NarrationImageFrameRead:
    return NarrationImageFrameRead.model_validate(frame)


def _reset_frame_for_regeneration(frame: NarrationImageFrame) -> None:
    if frame.output_image_path and os.path.exists(frame.output_image_path):
        os.remove(frame.output_image_path)
    frame.status = NarrationImageFrameStatus.PENDING.value
    frame.invokeai_generated_image_name = None
    frame.actual_seed = None
    frame.output_image_path = None
    frame.error_message = None
    if frame.mode == NarrationImageGenerationMode.IMAGE_TO_IMAGE.value:
        frame.invokeai_reference_image_name = None


def _collect_descendant_ids(
    series: NarrationImageSeries,
    root_frame_id: uuid.UUID,
) -> set[uuid.UUID]:
    by_parent: dict[uuid.UUID | None, list[NarrationImageFrame]] = {}
    for frame in series.frames:
        by_parent.setdefault(frame.parent_frame_id, []).append(frame)

    collected: set[uuid.UUID] = set()
    stack = [root_frame_id]
    while stack:
        current = stack.pop()
        if current in collected:
            continue
        collected.add(current)
        for child in by_parent.get(current, []):
            stack.append(child.id)
    return collected


def _queue_series(series: NarrationImageSeries) -> None:
    generate_narration_image_series.delay(str(series.id))


@router.get(
    "/api/segments/{segment_id}/image-series",
    response_model=list[NarrationImageSeriesRead],
)
def list_segment_image_series(segment_id: int, db: Session = Depends(get_db)):
    _get_segment_or_404(segment_id, db)
    rows = (
        db.query(NarrationImageSeries)
        .filter(NarrationImageSeries.segment_id == segment_id)
        .order_by(NarrationImageSeries.created_at.desc())
        .all()
    )
    return [_series_read(item) for item in rows]


@router.post(
    "/api/segments/{segment_id}/image-series",
    response_model=NarrationImageSeriesRead,
    status_code=201,
)
def create_segment_image_series(
    segment_id: int,
    data: NarrationImageSeriesCreate,
    db: Session = Depends(get_db),
):
    _get_segment_or_404(segment_id, db)

    if data.auto_generate:
        _assert_no_other_active_series(db)
    if data.auto_generate and not data.initial_prompt:
        raise HTTPException(
            status_code=400,
            detail="initial_prompt is required when auto_generate=true",
        )

    series = NarrationImageSeries(
        segment_id=segment_id,
        name=data.name.strip() if data.name else None,
        status=(
            NarrationImageSeriesStatus.QUEUED.value
            if data.auto_generate
            else NarrationImageSeriesStatus.DRAFT.value
        ),
        queued_at=_utc_now() if data.auto_generate else None,
    )
    db.add(series)
    db.flush()

    if data.initial_prompt:
        frame = NarrationImageFrame(
            series_id=series.id,
            parent_frame_id=None,
            step_key="manual_root",
            step_order=1,
            is_fork=False,
            prompt=data.initial_prompt.strip(),
            mode=NarrationImageGenerationMode.TEXT_TO_IMAGE.value,
            status=NarrationImageFrameStatus.PENDING.value,
            width=data.width,
            height=data.height,
            num_steps=data.num_steps,
            cfg_scale=data.cfg_scale,
            seed=data.seed,
        )
        db.add(frame)

    db.commit()
    db.refresh(series)

    if data.auto_generate:
        _queue_series(series)

    return _series_read(series)


@router.post(
    "/api/segments/{segment_id}/image-series/auto",
    response_model=NarrationImageSeriesRead,
    status_code=201,
)
def create_auto_segment_image_series(
    segment_id: int,
    data: NarrationImageSeriesAutoCreate,
    db: Session = Depends(get_db),
):
    segment = _get_segment_or_404(segment_id, db)
    _assert_no_other_active_series(db)

    try:
        plan = generate_image_sequence_plan(
            segment_text=segment.text,
            creative_direction=data.creative_direction,
            target_images=data.target_images,
        )
    except Exception as exc:
        logger.exception(
            "Failed to generate image sequence plan for segment %s",
            segment_id,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Failed to generate image sequence prompts: {exc}",
        )

    series = NarrationImageSeries(
        segment_id=segment_id,
        name=(data.name.strip() if data.name else None) or plan.series_name,
        source_prompt=data.creative_direction.strip(),
        plan_json=plan.model_dump(),
        status=NarrationImageSeriesStatus.QUEUED.value,
        queued_at=_utc_now(),
    )
    db.add(series)
    db.flush()

    step_frame_id_map: dict[str, uuid.UUID] = {}
    for index, step in enumerate(plan.steps, start=1):
        parent_frame_id = (
            step_frame_id_map.get(step.parent_id) if step.parent_id else None
        )
        frame = NarrationImageFrame(
            series_id=series.id,
            parent_frame_id=parent_frame_id,
            step_key=step.id,
            step_order=index,
            is_fork=step.is_fork,
            prompt=step.prompt.strip(),
            mode=step.mode,
            status=NarrationImageFrameStatus.PENDING.value,
            width=data.width,
            height=data.height,
            num_steps=data.num_steps,
            cfg_scale=data.cfg_scale,
            seed=data.seed,
        )
        db.add(frame)
        db.flush()
        step_frame_id_map[step.id] = frame.id

    db.commit()
    db.refresh(series)
    _queue_series(series)
    return _series_read(series)


@router.get("/api/image-series/{series_id}", response_model=NarrationImageSeriesRead)
def get_image_series(series_id: uuid.UUID, db: Session = Depends(get_db)):
    series = _get_series_or_404(series_id, db)
    return _series_read(series)


@router.post(
    "/api/image-series/{series_id}/generate", response_model=NarrationImageSeriesRead
)
def queue_image_series_generation(series_id: uuid.UUID, db: Session = Depends(get_db)):
    series = _get_series_or_404(series_id, db)
    if series.status in _ACTIVE_SERIES_STATES:
        raise HTTPException(
            status_code=400,
            detail="Image series is already queued or generating",
        )
    pending_count = (
        db.query(NarrationImageFrame)
        .filter(
            NarrationImageFrame.series_id == series.id,
            NarrationImageFrame.status == NarrationImageFrameStatus.PENDING.value,
        )
        .count()
    )
    if pending_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Image series has no pending frames",
        )

    _assert_no_other_active_series(db, exclude_series_id=series.id)
    series.status = NarrationImageSeriesStatus.QUEUED.value
    series.queued_at = _utc_now()
    series.error_message = None
    db.commit()
    db.refresh(series)
    _queue_series(series)
    return _series_read(series)


@router.post(
    "/api/image-series/{series_id}/frames", response_model=NarrationImageFrameRead
)
def add_image_series_frame(
    series_id: uuid.UUID,
    data: NarrationImageFrameCreate,
    db: Session = Depends(get_db),
):
    series = _get_series_or_404(series_id, db)
    if series.status in _ACTIVE_SERIES_STATES:
        raise HTTPException(
            status_code=400,
            detail="Cannot modify frames while series is queued or generating",
        )

    parent_frame = None
    if data.parent_frame_id is not None:
        parent_frame = _get_series_frame_or_404(series.id, data.parent_frame_id, db)

    mode = data.mode
    if not mode:
        mode = (
            NarrationImageGenerationMode.IMAGE_TO_IMAGE.value
            if parent_frame
            else NarrationImageGenerationMode.TEXT_TO_IMAGE.value
        )
    if (
        parent_frame is None
        and mode == NarrationImageGenerationMode.IMAGE_TO_IMAGE.value
    ):
        raise HTTPException(
            status_code=400,
            detail="image_to_image mode requires parent_frame_id",
        )

    next_order = (
        db.query(NarrationImageFrame.step_order)
        .filter(NarrationImageFrame.series_id == series.id)
        .order_by(NarrationImageFrame.step_order.desc())
        .limit(1)
        .scalar()
        or 0
    ) + 1

    frame = NarrationImageFrame(
        series_id=series.id,
        parent_frame_id=parent_frame.id if parent_frame else None,
        step_key=f"manual_{next_order}",
        step_order=next_order,
        is_fork=data.is_fork or bool(parent_frame),
        prompt=data.prompt.strip(),
        mode=mode,
        status=NarrationImageFrameStatus.PENDING.value,
        width=data.width,
        height=data.height,
        num_steps=data.num_steps,
        cfg_scale=data.cfg_scale,
        seed=data.seed,
    )
    db.add(frame)

    if series.status == NarrationImageSeriesStatus.COMPLETED.value:
        series.status = NarrationImageSeriesStatus.DRAFT.value
        series.completed_at = None

    db.commit()
    db.refresh(frame)
    return _frame_read(frame)


@router.post(
    "/api/image-series/{series_id}/frames/{frame_id}/regenerate",
    response_model=NarrationImageSeriesRead,
)
def regenerate_image_series_frame(
    series_id: uuid.UUID,
    frame_id: uuid.UUID,
    data: NarrationImageRegenerateRequest,
    db: Session = Depends(get_db),
):
    series = _get_series_or_404(series_id, db)
    _get_series_frame_or_404(series.id, frame_id, db)

    if series.status in _ACTIVE_SERIES_STATES:
        raise HTTPException(
            status_code=400,
            detail="Cannot regenerate frames while series is queued or generating",
        )
    if data.auto_generate:
        _assert_no_other_active_series(db, exclude_series_id=series.id)

    target_ids = (
        _collect_descendant_ids(series, frame_id)
        if data.include_descendants
        else {frame_id}
    )
    for frame in series.frames:
        if frame.id in target_ids:
            _reset_frame_for_regeneration(frame)

    series.status = (
        NarrationImageSeriesStatus.QUEUED.value
        if data.auto_generate
        else NarrationImageSeriesStatus.DRAFT.value
    )
    series.error_message = None
    series.completed_at = None
    series.queued_at = _utc_now() if data.auto_generate else None
    db.commit()
    db.refresh(series)

    if data.auto_generate:
        _queue_series(series)

    return _series_read(series)


@router.post(
    "/api/image-series/{series_id}/suggestions",
    response_model=NarrationImagePromptSuggestionResponse,
)
def suggest_image_series_prompts(
    series_id: uuid.UUID,
    data: NarrationImagePromptSuggestionRequest,
    db: Session = Depends(get_db),
):
    series = _get_series_or_404(series_id, db)

    source_frame: NarrationImageFrame | None = None
    if data.source_frame_id is not None:
        source_frame = _get_series_frame_or_404(series.id, data.source_frame_id, db)
    else:
        completed = [
            frame
            for frame in sorted(
                series.frames,
                key=lambda item: (item.step_order, item.created_at),
            )
            if frame.status == NarrationImageFrameStatus.COMPLETED.value
        ]
        source_frame = (
            completed[-1]
            if completed
            else (series.frames[-1] if series.frames else None)
        )

    if not source_frame:
        raise HTTPException(
            status_code=400,
            detail="Cannot suggest prompts for an empty image series",
        )

    try:
        suggestions = suggest_image_prompts(
            segment_text=series.segment.text,
            source_prompt=source_frame.prompt,
            guidance=data.guidance,
            count=data.count,
        )
    except Exception as exc:
        logger.exception("Failed prompt suggestion for series %s", series_id)
        raise HTTPException(
            status_code=502,
            detail=f"Prompt suggestion failed: {exc}",
        )

    return NarrationImagePromptSuggestionResponse(suggestions=suggestions)


@router.delete("/api/image-series/{series_id}", status_code=204)
def delete_image_series(series_id: uuid.UUID, db: Session = Depends(get_db)):
    series = _get_series_or_404(series_id, db)
    if series.status in _ACTIVE_SERIES_STATES:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete image series while it is queued or generating",
        )

    for frame in series.frames:
        if frame.output_image_path and os.path.exists(frame.output_image_path):
            os.remove(frame.output_image_path)

    series_dir = (
        Path(settings.media_dir)
        / str(series.segment.project_id)
        / "narration"
        / "image_series"
        / str(series.segment_id)
        / str(series.id)
    )
    if series_dir.exists():
        shutil.rmtree(series_dir, ignore_errors=True)

    db.delete(series)
    db.commit()
    return Response(status_code=204)
