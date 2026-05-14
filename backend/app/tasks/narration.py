from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models.narration import (
    NarrationSegment,
    NarrationTranscription,
    NarrationVariant,
    NarrationVoiceSample,
)
from app.services.client_factory import build_studio_voice_client
from app.services.narration.dia import generate as dia_generate
from app.services.narration.dia import get_wav_duration
from app.services.narration.events import (
    clear_narration_job,
    get_narration_active_job,
    increment_narration_queue_depth,
    is_narration_job_cancelled,
    mark_narration_job_progress,
    narration_queue_status_payload,
    publish_narration_event,
    set_narration_active_job,
)
from app.services.narration.magpie import generate as magpie_generate
from app.services.narration.quality import (
    NarrationQualityResult,
    evaluate_narration_quality,
)
from app.services.narration.sanitize import sanitize_text
from app.services.narration.stt import transcribe_audio_file
from app.services.narration.studio_voice import (
    STUDIO_VOICE_STATUS_CLEANED,
    STUDIO_VOICE_STATUS_ERROR,
    STUDIO_VOICE_STATUS_NOT_CLEANED,
    STUDIO_VOICE_STATUS_UNAVAILABLE,
    enhance_audio_file,
    is_studio_voice_ready,
    studio_voice_output_path,
)

logger = logging.getLogger(__name__)

MAX_GENERATION_ATTEMPTS = 3
QUALITY_ACCEPT_THRESHOLD = 8.0


@dataclass
class AttemptResult:
    attempt: int
    output_path: str
    duration_seconds: float
    studio_voice_audio_path: str | None
    studio_voice_status: str
    studio_voice_error_message: str | None
    studio_voice_cleaned_at: datetime | None
    transcription_text: str
    transcription_words: list[dict]
    quality: NarrationQualityResult
    variant_id: int


def _project_output_dir(project_id) -> Path:
    return Path(settings.media_dir) / str(project_id) / "narration"


def _safe_unlink(path: str | None) -> None:
    if not path:
        return
    try:
        if Path(path).exists():
            Path(path).unlink()
    except Exception:
        logger.warning("Failed to remove temporary audio path %s", path)


def _copy_variant_studio_voice_to_segment(
    segment: NarrationSegment,
    variant: NarrationVariant | None,
) -> None:
    if variant is None:
        segment.studio_voice_audio_path = None
        segment.studio_voice_status = STUDIO_VOICE_STATUS_NOT_CLEANED
        segment.studio_voice_error_message = None
        segment.studio_voice_cleaned_at = None
        return

    segment.studio_voice_audio_path = variant.studio_voice_audio_path
    segment.studio_voice_status = (
        variant.studio_voice_status or STUDIO_VOICE_STATUS_NOT_CLEANED
    )
    segment.studio_voice_error_message = variant.studio_voice_error_message
    segment.studio_voice_cleaned_at = variant.studio_voice_cleaned_at


def _has_cleaned_audio(path: str | None) -> bool:
    if not path:
        return False
    return Path(path).exists()


def _apply_studio_voice_result_to_variant(
    variant: NarrationVariant,
    *,
    status: str,
    output_path: str | None,
    error_message: str | None,
    cleaned_at: datetime | None,
) -> None:
    variant.studio_voice_status = status
    variant.studio_voice_audio_path = output_path
    variant.studio_voice_error_message = error_message
    variant.studio_voice_cleaned_at = cleaned_at


def _apply_studio_voice_result_to_segment(
    segment: NarrationSegment,
    *,
    status: str,
    output_path: str | None,
    error_message: str | None,
    cleaned_at: datetime | None,
) -> None:
    segment.studio_voice_status = status
    segment.studio_voice_audio_path = output_path
    segment.studio_voice_error_message = error_message
    segment.studio_voice_cleaned_at = cleaned_at


def _make_output_filename(position: int, text: str, variant_num: int = 0) -> str:
    clean = re.sub(r"\[S\d+\]\s*", "", text)
    words = clean.split()[:5]
    name = "_".join(words)
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name).lower()[:50]
    suffix = f"_v{variant_num}" if variant_num > 0 else ""
    return f"{position:03d}_{name}{suffix}.wav"


def _segment_payload(segment: NarrationSegment) -> dict:
    return {
        "id": segment.id,
        "project_id": str(segment.project_id),
        "position": segment.position,
        "text": segment.text,
        "sanitized_text": segment.sanitized_text,
        "service": segment.service,
        "status": segment.status,
        "audio_path": segment.audio_path,
        "studio_voice_audio_path": segment.studio_voice_audio_path,
        "studio_voice_status": segment.studio_voice_status,
        "studio_voice_error_message": segment.studio_voice_error_message,
        "studio_voice_cleaned_at": (
            segment.studio_voice_cleaned_at.isoformat()
            if segment.studio_voice_cleaned_at
            else None
        ),
        "duration_seconds": segment.duration_seconds,
        "error_message": segment.error_message,
        "selected_variant_id": segment.selected_variant_id,
        "voice_sample_id": segment.voice_sample_id,
        "magpie_voice": segment.magpie_voice,
        "original_text": segment.original_text,
        "quality_score": segment.quality_score,
        "needs_review": segment.needs_review,
        "is_final": segment.is_final,
        "last_generated_at": (
            segment.last_generated_at.isoformat() if segment.last_generated_at else None
        ),
        "generation_attempts": segment.generation_attempts,
        "created_at": segment.created_at.isoformat() if segment.created_at else None,
        "updated_at": segment.updated_at.isoformat() if segment.updated_at else None,
    }


def _upsert_transcription(
    db,
    segment_id: int,
    text: str,
    words: list[dict],
) -> NarrationTranscription:
    existing = (
        db.query(NarrationTranscription)
        .filter(NarrationTranscription.segment_id == segment_id)
        .first()
    )
    if existing:
        existing.text = text
        existing.words_json = words
        db.commit()
        db.refresh(existing)
        return existing

    transcription = NarrationTranscription(
        segment_id=segment_id,
        text=text,
        words_json=words,
    )
    db.add(transcription)
    db.commit()
    db.refresh(transcription)
    return transcription


def _publish_queue_status() -> None:
    publish_narration_event(narration_queue_status_payload())


def _publish_job_terminal_event(progress: dict) -> None:
    if progress["completed"] < progress["total"]:
        return

    if progress["cancelled"]:
        completed = progress["generated"] + progress["failed"]
        remaining = max(0, progress["total"] - completed)
        publish_narration_event(
            {
                "type": "job_cancelled",
                "job_id": progress["job_id"],
                "completed": completed,
                "remaining": remaining,
            }
        )
    else:
        publish_narration_event(
            {
                "type": "job_done",
                "job_id": progress["job_id"],
                "generated": progress["generated"],
                "failed": progress["failed"],
                "errors": [],
            }
        )

    clear_narration_job(progress["job_id"])


def _run_single_attempt(
    *,
    db,
    segment: NarrationSegment,
    raw_text: str,
    sanitized_text: str,
    attempt: int,
) -> AttemptResult:
    variant_num = (
        db.query(func.count(NarrationVariant.id))
        .filter(NarrationVariant.segment_id == segment.id)
        .scalar()
        or 0
    )

    output_dir = _project_output_dir(segment.project_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _make_output_filename(
        segment.position, raw_text, variant_num=variant_num
    )
    output_path = output_dir / filename

    logger.info(
        "Narration generation attempt %s/%s for segment %s (service=%s)",
        attempt,
        MAX_GENERATION_ATTEMPTS,
        segment.id,
        segment.service,
    )

    if segment.service == "dia":
        dia_kwargs = {}
        if segment.voice_sample_id:
            voice_sample = (
                db.query(NarrationVoiceSample)
                .filter(NarrationVoiceSample.id == segment.voice_sample_id)
                .first()
            )
            if voice_sample:
                dia_kwargs["reference_audio_path"] = voice_sample.audio_path
                if voice_sample.transcript:
                    dia_kwargs["reference_text_override"] = voice_sample.transcript
        asyncio.run(dia_generate(sanitized_text, str(output_path), **dia_kwargs))
    elif segment.service == "magpie":
        asyncio.run(
            magpie_generate(
                sanitized_text,
                str(output_path),
                voice=segment.magpie_voice or None,
            )
        )
    else:
        raise RuntimeError(f"Unknown service: {segment.service}")

    variant = NarrationVariant(
        segment_id=segment.id,
        text=raw_text,
        sanitized_text=sanitized_text,
        service=segment.service,
        audio_path=str(output_path),
        duration_seconds=round(get_wav_duration(str(output_path)), 2),
        studio_voice_status=STUDIO_VOICE_STATUS_NOT_CLEANED,
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)

    sv_client = build_studio_voice_client(db)
    if sv_client.auto_clean and variant.audio_path:
        studio_voice_result = asyncio.run(
            enhance_audio_file(
                variant.audio_path,
                output_audio_path=studio_voice_output_path(variant.audio_path),
                check_health=True,
                client=sv_client,
            )
        )
        variant.studio_voice_status = studio_voice_result.status
        variant.studio_voice_audio_path = studio_voice_result.output_path
        variant.studio_voice_error_message = studio_voice_result.error_message
        variant.studio_voice_cleaned_at = studio_voice_result.cleaned_at
        db.commit()
        db.refresh(variant)

    transcription_text = ""
    words: list[dict] = []
    try:
        transcription_text, words = asyncio.run(transcribe_audio_file(str(output_path)))
    except Exception as exc:
        logger.warning(
            "STT failed for segment %s attempt %s; keeping audio for review: %s",
            segment.id,
            attempt,
            exc,
        )

    quality = asyncio.run(
        evaluate_narration_quality(
            original_text=sanitized_text or raw_text,
            transcription_text=transcription_text,
        )
    )

    logger.info(
        "Narration quality for segment %s attempt %s: score=%s regenerate=%s reason=%s",
        segment.id,
        attempt,
        quality.score,
        quality.should_regenerate,
        quality.reason,
    )

    return AttemptResult(
        attempt=attempt,
        output_path=str(output_path),
        duration_seconds=variant.duration_seconds or 0.0,
        studio_voice_audio_path=variant.studio_voice_audio_path,
        studio_voice_status=variant.studio_voice_status,
        studio_voice_error_message=variant.studio_voice_error_message,
        studio_voice_cleaned_at=variant.studio_voice_cleaned_at,
        transcription_text=transcription_text,
        transcription_words=words,
        quality=quality,
        variant_id=variant.id,
    )


def _finalize_success(
    db,
    segment: NarrationSegment,
    result: AttemptResult,
    *,
    needs_review: bool = False,
) -> None:
    segment.status = "done"
    segment.audio_path = result.output_path
    segment.studio_voice_audio_path = result.studio_voice_audio_path
    segment.studio_voice_status = result.studio_voice_status
    segment.studio_voice_error_message = result.studio_voice_error_message
    segment.studio_voice_cleaned_at = result.studio_voice_cleaned_at
    segment.duration_seconds = result.duration_seconds
    segment.error_message = None
    segment.selected_variant_id = result.variant_id
    segment.quality_score = result.quality.score
    segment.needs_review = needs_review
    segment.is_final = False
    segment.generation_attempts = result.attempt

    _upsert_transcription(
        db,
        segment.id,
        result.transcription_text,
        result.transcription_words,
    )
    db.commit()
    db.refresh(segment)


def _finalize_needs_review(
    db,
    segment: NarrationSegment,
    best_result: AttemptResult | None,
    attempt_errors: list[str],
) -> None:
    segment.status = "error"
    segment.needs_review = True
    segment.is_final = False
    segment.generation_attempts = MAX_GENERATION_ATTEMPTS

    if best_result:
        segment.audio_path = best_result.output_path
        segment.studio_voice_audio_path = best_result.studio_voice_audio_path
        segment.studio_voice_status = best_result.studio_voice_status
        segment.studio_voice_error_message = best_result.studio_voice_error_message
        segment.studio_voice_cleaned_at = best_result.studio_voice_cleaned_at
        segment.duration_seconds = best_result.duration_seconds
        segment.selected_variant_id = best_result.variant_id
        segment.quality_score = best_result.quality.score
        segment.error_message = (
            f"Needs review: best quality score "
            f"{best_result.quality.score}/10 after {MAX_GENERATION_ATTEMPTS} attempts. "
            f"{best_result.quality.reason}"
        )[:1000]
        if best_result.transcription_text.strip() or best_result.transcription_words:
            _upsert_transcription(
                db,
                segment.id,
                best_result.transcription_text,
                best_result.transcription_words,
            )
        else:
            db.query(NarrationTranscription).filter(
                NarrationTranscription.segment_id == segment.id
            ).delete(synchronize_session=False)
    else:
        segment.audio_path = None
        segment.studio_voice_audio_path = None
        segment.studio_voice_status = STUDIO_VOICE_STATUS_NOT_CLEANED
        segment.studio_voice_error_message = None
        segment.studio_voice_cleaned_at = None
        segment.duration_seconds = None
        segment.selected_variant_id = None
        segment.quality_score = 0.0
        details = (
            " | ".join(attempt_errors[:3]) if attempt_errors else "Unknown failure"
        )
        segment.error_message = (
            f"Generation failed after {MAX_GENERATION_ATTEMPTS} attempts. {details}"
        )[:1000]

    db.commit()
    db.refresh(segment)


@celery.task(bind=True, max_retries=0, queue="dia")
def generate_narration_segment_task(
    self,
    *,
    segment_id: int,
    job_id: str,
    index: int,
    total: int,
    text_override: str | None = None,
    mark_needs_review: bool = False,
):
    set_narration_active_job(job_id)
    increment_narration_queue_depth(-1)
    _publish_queue_status()

    progress: dict | None = None
    db = SessionLocal()
    try:
        segment = (
            db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
        )
        if not segment:
            logger.error("Narration segment %s not found", segment_id)
            progress = mark_narration_job_progress(job_id, failed=True)
            return

        if is_narration_job_cancelled(job_id):
            logger.info(
                "Skipping segment %s because narration job %s is cancelled",
                segment_id,
                job_id,
            )
            progress = mark_narration_job_progress(job_id, skipped=True)
            return

        estimate = 45.0 if segment.service == "dia" else 3.0
        publish_narration_event(
            {
                "type": "segment_start",
                "job_id": job_id,
                "segment_id": segment_id,
                "index": index,
                "total": total,
                "estimate_seconds": estimate,
            }
        )
        segment_started_at = time.monotonic()

        segment.status = "generating"
        segment.error_message = None
        segment.needs_review = mark_needs_review
        segment.is_final = False
        segment.last_generated_at = datetime.now(timezone.utc)
        db.commit()

        raw_text = text_override if text_override else segment.text
        sanitized_text = sanitize_text(raw_text)

        best_result: AttemptResult | None = None
        attempt_errors: list[str] = []

        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            if is_narration_job_cancelled(job_id):
                logger.info(
                    "Stopping retries for segment %s because job %s is cancelled",
                    segment_id,
                    job_id,
                )
                progress = mark_narration_job_progress(job_id, skipped=True)
                return

            try:
                result = _run_single_attempt(
                    db=db,
                    segment=segment,
                    raw_text=raw_text,
                    sanitized_text=sanitized_text,
                    attempt=attempt,
                )
                if (best_result is None) or (
                    result.quality.score > best_result.quality.score
                ):
                    best_result = result

                should_retry = attempt < MAX_GENERATION_ATTEMPTS and (
                    result.quality.should_regenerate
                    or result.quality.score < QUALITY_ACCEPT_THRESHOLD
                )
                if should_retry:
                    logger.info(
                        "Regenerating segment %s after attempt %s (score=%s)",
                        segment_id,
                        attempt,
                        result.quality.score,
                    )
                    continue

                if (
                    result.quality.score >= QUALITY_ACCEPT_THRESHOLD
                    and not result.quality.should_regenerate
                ):
                    _finalize_success(
                        db,
                        segment,
                        result,
                        needs_review=mark_needs_review,
                    )
                    publish_narration_event(
                        {
                            "type": "segment_done",
                            "job_id": job_id,
                            "segment_id": segment_id,
                            "segment": _segment_payload(segment),
                            "index": index,
                            "total": total,
                            "generation_seconds": round(
                                time.monotonic() - segment_started_at, 1
                            ),
                            "quality_score": result.quality.score,
                            "generation_attempts": result.attempt,
                        }
                    )
                    progress = mark_narration_job_progress(job_id, generated=True)
                    return
            except Exception as exc:
                attempt_errors.append(str(exc))
                logger.warning(
                    "Narration attempt %s/%s failed for segment %s: %s",
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                    segment_id,
                    exc,
                )
                if attempt >= MAX_GENERATION_ATTEMPTS:
                    break

        _finalize_needs_review(db, segment, best_result, attempt_errors)
        publish_narration_event(
            {
                "type": "segment_error",
                "job_id": job_id,
                "segment_id": segment_id,
                "error": segment.error_message or "Needs review",
                "index": index,
                "total": total,
                "segment": _segment_payload(segment),
            }
        )
        progress = mark_narration_job_progress(job_id, failed=True)
    except Exception as exc:
        logger.exception("Narration pipeline failed for segment %s", segment_id)
        segment = (
            db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
        )
        if segment:
            segment.status = "error"
            segment.needs_review = mark_needs_review
            segment.is_final = False
            segment.error_message = str(exc)[:1000]
            db.commit()
        publish_narration_event(
            {
                "type": "segment_error",
                "job_id": job_id,
                "segment_id": segment_id,
                "error": str(exc),
                "index": index,
                "total": total,
            }
        )
        progress = mark_narration_job_progress(job_id, failed=True)
    finally:
        db.close()
        if get_narration_active_job() == job_id:
            set_narration_active_job(None)
        _publish_queue_status()

        if progress:
            _publish_job_terminal_event(progress)


@celery.task(bind=True, max_retries=0, queue="dia")
def clean_project_studio_voice_task(
    self,
    *,
    project_id: str,
) -> dict:
    db = SessionLocal()
    cleaned = 0
    skipped = 0
    failed = 0

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        logger.error(
            "Invalid project id for Studio Voice clean-all task: %s", project_id
        )
        return {
            "project_id": project_id,
            "cleaned": cleaned,
            "skipped": skipped,
            "failed": failed + 1,
            "error": "Invalid project id",
        }

    sv_client = build_studio_voice_client(db)
    try:
        if not asyncio.run(is_studio_voice_ready(client=sv_client)):
            logger.warning(
                "Studio Voice clean-all skipped for project %s: service unavailable",
                project_id,
            )
            return {
                "project_id": project_id,
                "cleaned": cleaned,
                "skipped": skipped,
                "failed": failed,
                "error": "Studio Voice service unavailable",
            }

        segments = (
            db.query(NarrationSegment)
            .filter(NarrationSegment.project_id == project_uuid)
            .order_by(NarrationSegment.position.asc())
            .all()
        )

        for segment in segments:
            variants = (
                db.query(NarrationVariant)
                .filter(NarrationVariant.segment_id == segment.id)
                .order_by(NarrationVariant.created_at.desc())
                .all()
            )

            if variants:
                for variant in variants:
                    if not variant.audio_path or not Path(variant.audio_path).exists():
                        skipped += 1
                        continue
                    if _has_cleaned_audio(variant.studio_voice_audio_path):
                        skipped += 1
                        continue

                    result = asyncio.run(
                        enhance_audio_file(
                            variant.audio_path,
                            output_audio_path=studio_voice_output_path(
                                variant.audio_path
                            ),
                            check_health=False,
                            client=sv_client,
                        )
                    )
                    _apply_studio_voice_result_to_variant(
                        variant,
                        status=result.status,
                        output_path=result.output_path,
                        error_message=result.error_message,
                        cleaned_at=result.cleaned_at,
                    )
                    if result.status == STUDIO_VOICE_STATUS_CLEANED:
                        cleaned += 1
                    elif result.status in {
                        STUDIO_VOICE_STATUS_ERROR,
                        STUDIO_VOICE_STATUS_UNAVAILABLE,
                    }:
                        failed += 1
                    else:
                        skipped += 1

                selected_variant = None
                if segment.selected_variant_id:
                    selected_variant = next(
                        (
                            variant
                            for variant in variants
                            if variant.id == segment.selected_variant_id
                        ),
                        None,
                    )
                if selected_variant is None and variants:
                    selected_variant = variants[0]
                _copy_variant_studio_voice_to_segment(segment, selected_variant)
                db.commit()
                continue

            if not segment.audio_path or not Path(segment.audio_path).exists():
                skipped += 1
                db.commit()
                continue

            if _has_cleaned_audio(segment.studio_voice_audio_path):
                skipped += 1
                db.commit()
                continue

            result = asyncio.run(
                enhance_audio_file(
                    segment.audio_path,
                    output_audio_path=studio_voice_output_path(segment.audio_path),
                    check_health=False,
                    client=sv_client,
                )
            )
            _apply_studio_voice_result_to_segment(
                segment,
                status=result.status,
                output_path=result.output_path,
                error_message=result.error_message,
                cleaned_at=result.cleaned_at,
            )
            if result.status == STUDIO_VOICE_STATUS_CLEANED:
                cleaned += 1
            elif result.status in {
                STUDIO_VOICE_STATUS_ERROR,
                STUDIO_VOICE_STATUS_UNAVAILABLE,
            }:
                failed += 1
            else:
                skipped += 1
            db.commit()

        return {
            "project_id": project_id,
            "cleaned": cleaned,
            "skipped": skipped,
            "failed": failed,
        }
    except Exception:
        logger.exception(
            "Studio Voice clean-all failed for project %s",
            project_id,
        )
        return {
            "project_id": project_id,
            "cleaned": cleaned,
            "skipped": skipped,
            "failed": failed + 1,
            "error": "Unexpected Studio Voice clean-all failure",
        }
    finally:
        db.close()
