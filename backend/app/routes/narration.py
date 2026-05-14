import asyncio
import io
import json
import logging
import os
import re
import shutil
import uuid
import zipfile
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
import redis.asyncio as redis_async
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.narration import (
    NarrationSegment,
    NarrationTranscription,
    NarrationVariant,
    NarrationVoiceSample,
)
from app.models.narration_image import (
    NarrationImageFrame,
    NarrationImageFrameStatus,
    NarrationImageSeries,
)
from app.models.project import Project, ProjectType
from app.services.client_factory import build_studio_voice_client
from app.services.narration.audio import (
    concatenate_segments,
    export_audio,
    load_and_normalize,
    trim_audio,
)
from app.services.narration.dia import get_wav_duration
from app.services.narration.events import (
    NARRATION_EVENTS_CHANNEL,
    get_narration_active_job,
    increment_narration_queue_depth,
    init_narration_job,
    is_narration_job_cancelled,
    mark_narration_job_cancelled,
    narration_queue_status_payload,
)
from app.services.narration.magpie import list_voices
from app.services.narration.sanitize import sanitize_text
from app.services.narration.stt import transcribe_audio_file
from app.services.narration.studio_voice import (
    STUDIO_VOICE_STATUS_NOT_CLEANED,
    enhance_audio_file,
    studio_voice_output_path,
)
from app.tasks.narration import (
    clean_project_studio_voice_task,
    generate_narration_segment_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["narration"])

STT_URL = os.environ.get("STT_URL", "http://192.168.5.96:8001")
NARRATION_ROOT = Path(settings.media_dir) / "narration"
VOICE_SAMPLES_DIR = NARRATION_ROOT / "voice_samples"
VOICE_SAMPLE_DRAFTS_DIR = VOICE_SAMPLES_DIR / "drafts"
VOICE_SAMPLE_ALLOWED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".opus",
    ".webm",
    ".mp4",
    ".mov",
    ".m4v",
    ".mkv",
    ".avi",
}
DEFAULT_SPLIT_TARGET_WORDS = 32
MIN_SPLIT_TARGET_WORDS = 8
MAX_SPLIT_TARGET_WORDS = 120
SPLIT_MIN_RATIO = 0.7
SPLIT_MAX_RATIO = 1.3
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z0-9']+")


def _safe_unlink(path: str | None) -> None:
    if path and os.path.exists(path):
        os.remove(path)


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", value)


def _voice_sample_output_path(name: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    token = uuid.uuid4().hex[:8]
    return VOICE_SAMPLES_DIR / f"{_safe_slug(name.lower())}_{stamp}_{token}.wav"


def _voice_sample_draft_to_dict(draft: "VoiceSampleDraft") -> dict:
    duration = 0.0
    if os.path.exists(draft.audio_path):
        with suppress(Exception):
            duration = get_wav_duration(draft.audio_path)
    return {
        "id": draft.id,
        "audio_path": draft.audio_path,
        "original_filename": draft.original_filename,
        "transcription": draft.transcription,
        "words": draft.words,
        "duration_seconds": round(duration, 2),
        "created_at": draft.created_at,
    }


def _is_allowed_voice_clip(file: UploadFile) -> bool:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension and extension in VOICE_SAMPLE_ALLOWED_EXTENSIONS:
        return True

    content_type = (file.content_type or "").lower()
    return content_type.startswith("audio/") or content_type.startswith("video/")


def _get_voice_sample_draft_or_404(draft_id: str) -> "VoiceSampleDraft":
    draft = voice_sample_drafts.get(draft_id)
    if not draft:
        raise HTTPException(404, "Voice sample draft not found")
    if not draft.audio_path or not os.path.exists(draft.audio_path):
        _cleanup_voice_sample_draft(draft_id)
        raise HTTPException(404, "Voice sample draft audio not found")
    return draft


def _cleanup_voice_sample_draft(draft_id: str) -> None:
    draft = voice_sample_drafts.pop(draft_id, None)
    if not draft:
        return
    _safe_unlink(draft.audio_path)
    _safe_unlink(draft.source_path)


def _extract_voice_clip_to_wav(source_path: Path, destination_path: Path) -> None:
    try:
        clip = load_and_normalize(str(source_path))
        clip.export(destination_path, format="wav")
    except Exception as exc:
        raise HTTPException(400, f"Unsupported audio/video clip: {exc}")


async def _create_voice_sample_draft_from_upload(
    clip: UploadFile,
    *,
    transcribe: bool = True,
) -> "VoiceSampleDraft":
    if not _is_allowed_voice_clip(clip):
        raise HTTPException(
            400,
            "Unsupported file type. Please upload an audio or video clip.",
        )

    content = await clip.read()
    if not content:
        raise HTTPException(400, "Uploaded clip is empty")

    VOICE_SAMPLE_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    draft_id = uuid.uuid4().hex
    original_filename = clip.filename or "voice_clip"
    extension = Path(original_filename).suffix.lower() or ".bin"
    safe_source_name = _safe_slug(f"{draft_id}_src{extension}")
    source_path = VOICE_SAMPLE_DRAFTS_DIR / safe_source_name
    audio_path = VOICE_SAMPLE_DRAFTS_DIR / f"{draft_id}.wav"

    source_path.write_bytes(content)
    try:
        _extract_voice_clip_to_wav(source_path, audio_path)
    except Exception:
        _safe_unlink(str(source_path))
        _safe_unlink(str(audio_path))
        raise

    transcription = ""
    words: list[dict] = []
    if transcribe:
        try:
            transcription, words = await _transcribe_audio_file_or_502(str(audio_path))
        except Exception:
            _safe_unlink(str(source_path))
            _safe_unlink(str(audio_path))
            raise

    draft = VoiceSampleDraft(
        id=draft_id,
        audio_path=str(audio_path),
        source_path=str(source_path),
        original_filename=original_filename,
        transcription=transcription,
        words=words,
    )
    voice_sample_drafts[draft.id] = draft
    return draft


def _project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _segment_to_dict(segment: NarrationSegment) -> dict:
    return {
        "id": segment.id,
        "project_id": segment.project_id,
        "position": segment.position,
        "text": segment.text,
        "sanitized_text": segment.sanitized_text,
        "service": segment.service,
        "status": segment.status,
        "audio_path": segment.audio_path,
        "studio_voice_audio_path": segment.studio_voice_audio_path,
        "studio_voice_status": segment.studio_voice_status,
        "studio_voice_error_message": segment.studio_voice_error_message,
        "studio_voice_cleaned_at": segment.studio_voice_cleaned_at,
        "duration_seconds": segment.duration_seconds,
        "error_message": segment.error_message,
        "quality_score": segment.quality_score,
        "needs_review": segment.needs_review,
        "is_final": segment.is_final,
        "last_generated_at": segment.last_generated_at,
        "generation_attempts": segment.generation_attempts,
        "selected_variant_id": segment.selected_variant_id,
        "voice_sample_id": segment.voice_sample_id,
        "magpie_voice": segment.magpie_voice,
        "original_text": segment.original_text,
        "created_at": segment.created_at,
        "updated_at": segment.updated_at,
    }


def _variant_to_dict(variant: NarrationVariant) -> dict:
    return {
        "id": variant.id,
        "segment_id": variant.segment_id,
        "text": variant.text,
        "sanitized_text": variant.sanitized_text,
        "service": variant.service,
        "audio_path": variant.audio_path,
        "studio_voice_audio_path": variant.studio_voice_audio_path,
        "studio_voice_status": variant.studio_voice_status,
        "studio_voice_error_message": variant.studio_voice_error_message,
        "studio_voice_cleaned_at": variant.studio_voice_cleaned_at,
        "duration_seconds": variant.duration_seconds,
        "created_at": variant.created_at,
    }


def _voice_sample_to_dict(sample: NarrationVoiceSample) -> dict:
    return {
        "id": sample.id,
        "name": sample.name,
        "audio_path": sample.audio_path,
        "transcript": sample.transcript,
        "created_at": sample.created_at,
    }


def _transcription_to_dict(transcription: NarrationTranscription) -> dict:
    return {
        "id": transcription.id,
        "segment_id": transcription.segment_id,
        "text": transcription.text,
        "words": transcription.words_json or [],
        "created_at": transcription.created_at,
    }


def _get_narration_project_or_404(project_id: uuid.UUID, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.project_type != ProjectType.NARRATION.value:
        raise HTTPException(
            status_code=400,
            detail="Narration endpoints require a project of type 'narration'",
        )
    return project


def _list_segments(project_id: uuid.UUID, db: Session) -> list[NarrationSegment]:
    return (
        db.query(NarrationSegment)
        .filter(NarrationSegment.project_id == project_id)
        .order_by(NarrationSegment.position.asc())
        .all()
    )


def _list_variants(segment_id: int, db: Session) -> list[NarrationVariant]:
    return (
        db.query(NarrationVariant)
        .filter(NarrationVariant.segment_id == segment_id)
        .order_by(NarrationVariant.created_at.desc())
        .all()
    )


def _resolve_existing_segment_audio_path(
    segment: NarrationSegment,
    db: Session,
    *,
    persist: bool = True,
) -> str | None:
    if segment.audio_path and os.path.exists(segment.audio_path):
        return segment.audio_path

    variants = _list_variants(segment.id, db)

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
    if (
        selected_variant
        and selected_variant.audio_path
        and os.path.exists(selected_variant.audio_path)
    ):
        segment.audio_path = selected_variant.audio_path
        if persist:
            db.commit()
            db.refresh(segment)
        return segment.audio_path

    fallback_variant = next(
        (
            variant
            for variant in variants
            if variant.audio_path and os.path.exists(variant.audio_path)
        ),
        None,
    )
    if not fallback_variant:
        return None

    segment.audio_path = fallback_variant.audio_path
    segment.selected_variant_id = fallback_variant.id
    if persist:
        db.commit()
        db.refresh(segment)
    return segment.audio_path


def _resolve_existing_segment_cleaned_audio_path(
    segment: NarrationSegment,
    db: Session,
    *,
    persist: bool = True,
) -> str | None:
    if segment.studio_voice_audio_path and os.path.exists(
        segment.studio_voice_audio_path
    ):
        return segment.studio_voice_audio_path

    variants = _list_variants(segment.id, db)

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

    candidate = None
    if (
        selected_variant
        and selected_variant.studio_voice_audio_path
        and os.path.exists(selected_variant.studio_voice_audio_path)
    ):
        candidate = selected_variant
    else:
        candidate = next(
            (
                variant
                for variant in variants
                if variant.studio_voice_audio_path
                and os.path.exists(variant.studio_voice_audio_path)
            ),
            None,
        )

    if not candidate:
        return None

    segment.studio_voice_audio_path = candidate.studio_voice_audio_path
    segment.studio_voice_status = candidate.studio_voice_status
    segment.studio_voice_error_message = candidate.studio_voice_error_message
    segment.studio_voice_cleaned_at = candidate.studio_voice_cleaned_at
    if persist:
        db.commit()
        db.refresh(segment)
    return segment.studio_voice_audio_path


def _compute_waveform_samples(audio_path: str, points: int) -> tuple[list[float], int]:
    clip = load_and_normalize(audio_path)
    samples = clip.get_array_of_samples()
    duration_ms = max(1, len(clip))

    if not samples:
        return [0.0 for _ in range(points)], duration_ms

    total_samples = len(samples)
    bucket_size = max(1, total_samples // points)
    averaged: list[float] = []
    max_value = 0.0

    for index in range(points):
        start = index * bucket_size
        if start >= total_samples:
            averaged.append(0.0)
            continue
        end = min(total_samples, start + bucket_size)
        if end <= start:
            averaged.append(0.0)
            continue

        abs_sum = 0.0
        for sample in samples[start:end]:
            abs_sum += abs(float(sample))
        value = abs_sum / (end - start)
        averaged.append(value)
        if value > max_value:
            max_value = value

    if max_value <= 0:
        normalized = [0.0 for _ in averaged]
    else:
        normalized = [round(value / max_value, 6) for value in averaged]

    return normalized, duration_ms


def _collect_project_audio_paths(project_id: uuid.UUID, db: Session) -> list[str]:
    segment_paths = (
        db.query(NarrationSegment.audio_path, NarrationSegment.studio_voice_audio_path)
        .filter(
            NarrationSegment.project_id == project_id,
            (
                NarrationSegment.audio_path.isnot(None)
                | NarrationSegment.studio_voice_audio_path.isnot(None)
            ),
        )
        .all()
    )
    variant_paths = (
        db.query(NarrationVariant.audio_path, NarrationVariant.studio_voice_audio_path)
        .join(NarrationSegment, NarrationVariant.segment_id == NarrationSegment.id)
        .filter(
            NarrationSegment.project_id == project_id,
            (
                NarrationVariant.audio_path.isnot(None)
                | NarrationVariant.studio_voice_audio_path.isnot(None)
            ),
        )
        .all()
    )
    collected = set()
    for source_path, cleaned_path in segment_paths + variant_paths:
        if source_path:
            collected.add(source_path)
        if cleaned_path:
            collected.add(cleaned_path)
    return sorted(collected)


def _collect_segment_audio_paths(segment_id: int, db: Session) -> list[str]:
    segment_path = (
        db.query(NarrationSegment.audio_path, NarrationSegment.studio_voice_audio_path)
        .filter(
            NarrationSegment.id == segment_id,
            (
                NarrationSegment.audio_path.isnot(None)
                | NarrationSegment.studio_voice_audio_path.isnot(None)
            ),
        )
        .all()
    )
    variant_paths = (
        db.query(NarrationVariant.audio_path, NarrationVariant.studio_voice_audio_path)
        .filter(
            NarrationVariant.segment_id == segment_id,
            (
                NarrationVariant.audio_path.isnot(None)
                | NarrationVariant.studio_voice_audio_path.isnot(None)
            ),
        )
        .all()
    )
    unique = set()
    for source_path, cleaned_path in segment_path + variant_paths:
        if source_path:
            unique.add(source_path)
        if cleaned_path:
            unique.add(cleaned_path)
    return sorted(unique)


def _count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def _normalize_sentence_spacing(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_into_sentences(text: str) -> list[str]:
    normalized = _normalize_sentence_spacing(text)
    if not normalized:
        return []
    sentences = [part.strip() for part in SENTENCE_SPLIT_RE.split(normalized) if part]
    return sentences or [normalized]


def _word_bounds_for_target(target_words: int) -> tuple[int, int]:
    min_words = max(MIN_SPLIT_TARGET_WORDS, int(round(target_words * SPLIT_MIN_RATIO)))
    max_words = min(MAX_SPLIT_TARGET_WORDS, int(round(target_words * SPLIT_MAX_RATIO)))
    if max_words < min_words:
        max_words = min_words
    return min_words, max_words


def _group_penalty(
    *,
    word_count: int,
    target_words: int,
    min_words: int,
    max_words: int,
) -> float:
    if min_words <= word_count <= max_words:
        return abs(word_count - target_words)
    if word_count < min_words:
        return (min_words - word_count) * 8 + abs(word_count - target_words)
    return (word_count - max_words) * 6 + abs(word_count - target_words)


def _split_sentence_groups(
    sentences: list[str],
    *,
    target_words: int,
    min_words: int,
    max_words: int,
) -> list[list[str]]:
    if not sentences:
        return []

    n = len(sentences)
    sentence_word_counts = [_count_words(sentence) for sentence in sentences]
    prefix_words = [0]
    for count in sentence_word_counts:
        prefix_words.append(prefix_words[-1] + count)

    def span_words(start: int, end: int) -> int:
        return prefix_words[end] - prefix_words[start]

    best_cost = [float("inf")] * (n + 1)
    next_break = [n] * (n + 1)
    best_cost[n] = 0.0

    for start in range(n - 1, -1, -1):
        for end in range(start + 1, n + 1):
            word_count = span_words(start, end)
            penalty = _group_penalty(
                word_count=word_count,
                target_words=target_words,
                min_words=min_words,
                max_words=max_words,
            )
            total_cost = penalty + best_cost[end]

            if total_cost < best_cost[start]:
                best_cost[start] = total_cost
                next_break[start] = end

            if word_count > (max_words * 2) and end > start + 1:
                break

    groups: list[list[str]] = []
    index = 0
    while index < n:
        next_index = next_break[index]
        if next_index <= index:
            next_index = index + 1
        groups.append(sentences[index:next_index])
        index = next_index

    return groups


def _build_split_groups(
    text: str,
    target_words: int,
) -> tuple[list[dict], int, int]:
    min_words, max_words = _word_bounds_for_target(target_words)
    sentences = _split_into_sentences(text)
    sentence_groups = _split_sentence_groups(
        sentences,
        target_words=target_words,
        min_words=min_words,
        max_words=max_words,
    )

    groups: list[dict] = []
    for sentence_group in sentence_groups:
        group_text = _normalize_sentence_spacing(" ".join(sentence_group))
        if not group_text:
            continue
        groups.append(
            {
                "text": group_text,
                "word_count": _count_words(group_text),
                "sentence_count": len(sentence_group),
            }
        )

    return groups, min_words, max_words


def _upsert_transcription(
    db: Session,
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
        existing.created_at = datetime.now(timezone.utc)
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


@dataclass
class VoiceSampleDraft:
    id: str
    audio_path: str
    source_path: str | None
    original_filename: str
    transcription: str = ""
    words: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


voice_sample_drafts: dict[str, VoiceSampleDraft] = {}


# --- Generation queue infrastructure ---


@dataclass
class GenerationJob:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    segment_ids: list[int] = field(default_factory=list)
    text_overrides: dict[int, str] = field(default_factory=dict)
    review_segment_ids: list[int] = field(default_factory=list)
    project_id: uuid.UUID | None = None


ws_clients: set[WebSocket] = set()
_redis_listener_task: asyncio.Task | None = None


async def _broadcast(message: dict):
    dead = set()
    data = json.dumps(jsonable_encoder(message), default=str)
    for ws in ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


def _queue_status() -> dict:
    return narration_queue_status_payload()


async def _redis_event_listener():
    client = redis_async.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(NARRATION_EVENTS_CHANNEL)
    logger.info("Subscribed to narration event channel: %s", NARRATION_EVENTS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            raw = message.get("data")
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                logger.warning("Skipping invalid narration event payload")
                continue
            await _broadcast(payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Narration redis listener failed")
    finally:
        with suppress(Exception):
            await pubsub.unsubscribe(NARRATION_EVENTS_CHANNEL)
        with suppress(Exception):
            await pubsub.aclose()
        with suppress(Exception):
            await client.aclose()


async def _seed_default_voice_sample():
    if not VOICE_SAMPLES_DIR.exists():
        VOICE_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        count = db.query(func.count(NarrationVoiceSample.id)).scalar() or 0
        if count > 0:
            return

        sample_audio = (
            Path(__file__).resolve().parents[1]
            / "services"
            / "narration"
            / "sample"
            / "Alice.wav"
        )
        sample_text = (
            Path(__file__).resolve().parents[1]
            / "services"
            / "narration"
            / "sample"
            / "text.txt"
        )
        if not sample_audio.exists():
            return

        transcript = sample_text.read_text().strip() if sample_text.exists() else ""
        destination = VOICE_SAMPLES_DIR / "Alice.wav"
        if not destination.exists():
            shutil.copy2(sample_audio, destination)

        sample = NarrationVoiceSample(
            name="Alice",
            audio_path=str(destination),
            transcript=transcript,
        )
        db.add(sample)
        db.commit()
        logger.info("Seeded default narration voice sample: Alice")


@router.on_event("startup")
async def _startup_narration():
    global _redis_listener_task
    NARRATION_ROOT.mkdir(parents=True, exist_ok=True)
    VOICE_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    if VOICE_SAMPLE_DRAFTS_DIR.exists():
        shutil.rmtree(VOICE_SAMPLE_DRAFTS_DIR, ignore_errors=True)
    VOICE_SAMPLE_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    voice_sample_drafts.clear()
    await _seed_default_voice_sample()
    if _redis_listener_task is None or _redis_listener_task.done():
        _redis_listener_task = asyncio.create_task(_redis_event_listener())


@router.on_event("shutdown")
async def _shutdown_narration():
    global _redis_listener_task
    if _redis_listener_task:
        _redis_listener_task.cancel()
        with suppress(asyncio.CancelledError):
            await _redis_listener_task
    _redis_listener_task = None


# --- Pydantic models ---


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class SegmentCreate(BaseModel):
    text: str
    position: int | None = None
    service: str = "dia"
    voice_sample_id: int | None = None
    magpie_voice: str | None = None


class SegmentUpdate(BaseModel):
    text: str | None = None
    position: int | None = None
    service: str | None = None
    voice_sample_id: int | None = None
    magpie_voice: str | None = None


class SegmentFlagsUpdate(BaseModel):
    is_final: bool | None = None
    needs_review: bool | None = None


class SegmentSplitRequest(BaseModel):
    target_words: int = Field(
        default=DEFAULT_SPLIT_TARGET_WORDS,
        ge=MIN_SPLIT_TARGET_WORDS,
        le=MAX_SPLIT_TARGET_WORDS,
    )


class ReorderItem(BaseModel):
    id: int
    position: int


class ReorderRequest(BaseModel):
    ordering: list[ReorderItem]


class ImportRequest(BaseModel):
    text: str
    service: str = "dia"
    magpie_voice: str | None = None
    original_texts: list[str] | None = None


class ImportArticleRequest(BaseModel):
    text: str
    service: str = "dia"
    magpie_voice: str | None = None


class SyncRequest(BaseModel):
    lines: list[str]
    service: str = "dia"


class RegenerateRequest(BaseModel):
    text: str | None = None


class TrimRequest(BaseModel):
    start_ms: int
    end_ms: int
    mode: Literal["keep", "remove"] = "keep"


class VoiceSampleDraftTrimRequest(BaseModel):
    start_ms: int
    end_ms: int


class VoiceSampleDraftFinalizeRequest(BaseModel):
    name: str
    transcript: str = ""


class VoiceSampleUpdateRequest(BaseModel):
    transcript: str


class ProcessChunkRequest(BaseModel):
    text: str


# --- Projects ---


@router.get("/api/projects")
async def api_list_projects(db: Session = Depends(get_db)):
    projects = (
        db.query(Project)
        .filter(Project.project_type == ProjectType.NARRATION.value)
        .order_by(Project.updated_at.desc())
        .all()
    )
    return [_project_to_dict(project) for project in projects]


@router.post("/api/projects", status_code=201)
async def api_create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        name=body.name,
        description=body.description,
        project_type=ProjectType.NARRATION.value,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_to_dict(project)


@router.get("/api/projects/{project_id}")
async def api_get_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    project = _get_narration_project_or_404(project_id, db)
    return _project_to_dict(project)


@router.put("/api/projects/{project_id}")
async def api_update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
):
    project = _get_narration_project_or_404(project_id, db)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    db.commit()
    db.refresh(project)
    return _project_to_dict(project)


@router.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    project = _get_narration_project_or_404(project_id, db)

    for path in _collect_project_audio_paths(project_id, db):
        _safe_unlink(path)

    project_media = Path(settings.media_dir) / str(project_id)
    if project_media.exists():
        shutil.rmtree(project_media)

    db.delete(project)
    db.commit()
    return {"ok": True}


# --- Segments ---


@router.get("/api/projects/{project_id}/segments")
async def api_list_segments(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_narration_project_or_404(project_id, db)
    segments = _list_segments(project_id, db)
    return [_segment_to_dict(segment) for segment in segments]


@router.post("/api/projects/{project_id}/segments", status_code=201)
async def api_create_segment(
    project_id: uuid.UUID,
    body: SegmentCreate,
    db: Session = Depends(get_db),
):
    _get_narration_project_or_404(project_id, db)

    sanitized = sanitize_text(body.text)
    if body.position is None:
        max_position = (
            db.query(func.max(NarrationSegment.position))
            .filter(NarrationSegment.project_id == project_id)
            .scalar()
        )
        position = (max_position or 0) + 1
    else:
        position = body.position
        db.query(NarrationSegment).filter(
            NarrationSegment.project_id == project_id,
            NarrationSegment.position >= position,
        ).update(
            {NarrationSegment.position: NarrationSegment.position + 1},
            synchronize_session=False,
        )

    segment = NarrationSegment(
        project_id=project_id,
        text=body.text,
        sanitized_text=sanitized,
        position=position,
        service=body.service,
        status="pending",
        voice_sample_id=body.voice_sample_id,
        magpie_voice=body.magpie_voice,
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return _segment_to_dict(segment)


@router.put("/api/segments/{segment_id}")
async def api_update_segment(
    segment_id: int,
    body: SegmentUpdate,
    db: Session = Depends(get_db),
):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    if body.text is not None:
        segment.text = body.text
        segment.sanitized_text = sanitize_text(body.text)
        segment.status = "pending"
        segment.audio_path = None
        segment.studio_voice_audio_path = None
        segment.studio_voice_status = STUDIO_VOICE_STATUS_NOT_CLEANED
        segment.studio_voice_error_message = None
        segment.studio_voice_cleaned_at = None
        segment.duration_seconds = None
        segment.error_message = None
        segment.quality_score = None
        segment.needs_review = False
        segment.is_final = False
        segment.last_generated_at = None
        segment.generation_attempts = 0
        segment.selected_variant_id = None
        db.query(NarrationTranscription).filter(
            NarrationTranscription.segment_id == segment.id
        ).delete(synchronize_session=False)
    if body.position is not None:
        segment.position = body.position
    if body.service is not None:
        segment.service = body.service
    if body.voice_sample_id is not None:
        segment.voice_sample_id = (
            body.voice_sample_id if body.voice_sample_id > 0 else None
        )
    if body.magpie_voice is not None:
        segment.magpie_voice = body.magpie_voice if body.magpie_voice else None

    db.commit()
    db.refresh(segment)
    return _segment_to_dict(segment)


@router.patch("/api/segments/{segment_id}/flags")
async def api_update_segment_flags(
    segment_id: int,
    body: SegmentFlagsUpdate,
    db: Session = Depends(get_db),
):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    if body.is_final is None and body.needs_review is None:
        raise HTTPException(400, "No segment flags provided")

    if body.is_final is not None:
        segment.is_final = body.is_final
        if body.is_final:
            segment.needs_review = False

    if body.needs_review is not None:
        segment.needs_review = body.needs_review
        if body.needs_review:
            segment.is_final = False

    db.commit()
    db.refresh(segment)
    return _segment_to_dict(segment)


@router.post("/api/segments/{segment_id}/mark-done")
async def api_mark_segment_done(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    audio_path = _resolve_existing_segment_audio_path(segment, db)
    if not audio_path:
        raise HTTPException(400, "Segment has no audio to mark done")

    segment.status = "done"
    segment.error_message = None
    segment.needs_review = False
    if segment.duration_seconds is None:
        with suppress(Exception):
            segment.duration_seconds = round(get_wav_duration(audio_path), 2)

    db.commit()
    db.refresh(segment)
    return _segment_to_dict(segment)


@router.post("/api/segments/{segment_id}/split/preview")
async def api_preview_split_segment(
    segment_id: int,
    body: SegmentSplitRequest,
    db: Session = Depends(get_db),
):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    groups, min_words, max_words = _build_split_groups(
        segment.text,
        body.target_words,
    )

    return {
        "segment_id": segment.id,
        "target_words": body.target_words,
        "min_words": min_words,
        "max_words": max_words,
        "can_split": len(groups) > 1,
        "groups": groups,
    }


@router.post("/api/segments/{segment_id}/split")
async def api_split_segment(
    segment_id: int,
    body: SegmentSplitRequest,
    db: Session = Depends(get_db),
):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    groups, min_words, max_words = _build_split_groups(
        segment.text,
        body.target_words,
    )
    if len(groups) < 2:
        raise HTTPException(
            400,
            "Segment could not be split into multiple sentence groups",
        )

    project_id = segment.project_id
    original_position = segment.position
    service = segment.service
    voice_sample_id = segment.voice_sample_id
    magpie_voice = segment.magpie_voice
    original_text = segment.original_text
    audio_paths_to_delete = _collect_segment_audio_paths(segment.id, db)

    position_delta = len(groups) - 1
    if position_delta > 0:
        db.query(NarrationSegment).filter(
            NarrationSegment.project_id == project_id,
            NarrationSegment.position > original_position,
        ).update(
            {NarrationSegment.position: NarrationSegment.position + position_delta},
            synchronize_session=False,
        )

    db.delete(segment)

    for index, group in enumerate(groups):
        text = group["text"]
        db.add(
            NarrationSegment(
                project_id=project_id,
                position=original_position + index,
                text=text,
                sanitized_text=sanitize_text(text),
                service=service,
                status="pending",
                voice_sample_id=voice_sample_id,
                magpie_voice=magpie_voice,
                original_text=original_text,
            )
        )

    db.commit()

    for path in audio_paths_to_delete:
        _safe_unlink(path)

    return {
        "project_id": project_id,
        "replaced_segment_id": segment_id,
        "target_words": body.target_words,
        "min_words": min_words,
        "max_words": max_words,
        "created_count": len(groups),
        "segments": [_segment_to_dict(item) for item in _list_segments(project_id, db)],
    }


@router.delete("/api/segments/{segment_id}")
async def api_delete_segment(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    _safe_unlink(segment.audio_path)
    _safe_unlink(segment.studio_voice_audio_path)

    variants = _list_variants(segment_id, db)
    for variant in variants:
        _safe_unlink(variant.audio_path)
        _safe_unlink(variant.studio_voice_audio_path)

    image_series_dir = (
        Path(settings.media_dir)
        / str(segment.project_id)
        / "narration"
        / "image_series"
        / str(segment.id)
    )
    if image_series_dir.exists():
        shutil.rmtree(image_series_dir, ignore_errors=True)

    db.delete(segment)
    db.commit()
    return {"ok": True}


@router.post("/api/segments/reorder")
async def api_reorder_segments(body: ReorderRequest, db: Session = Depends(get_db)):
    first_segment_id = body.ordering[0].id if body.ordering else None
    for item in body.ordering:
        db.query(NarrationSegment).filter(NarrationSegment.id == item.id).update(
            {NarrationSegment.position: item.position},
            synchronize_session=False,
        )
    db.commit()

    if not first_segment_id:
        return []

    first_segment = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == first_segment_id)
        .first()
    )
    if not first_segment:
        return []

    segments = _list_segments(first_segment.project_id, db)
    return [_segment_to_dict(segment) for segment in segments]


@router.post("/api/projects/{project_id}/segments/import")
async def api_import_segments(
    project_id: uuid.UUID,
    body: ImportRequest,
    db: Session = Depends(get_db),
):
    _get_narration_project_or_404(project_id, db)
    lines = [line.strip() for line in body.text.splitlines() if line.strip()]
    if not lines:
        raise HTTPException(400, "No lines to import")

    for path in _collect_project_audio_paths(project_id, db):
        _safe_unlink(path)

    db.query(NarrationSegment).filter(NarrationSegment.project_id == project_id).delete(
        synchronize_session=False,
    )

    created_segments: list[NarrationSegment] = []
    for index, line in enumerate(lines, start=1):
        original = None
        if body.original_texts and index - 1 < len(body.original_texts):
            original = body.original_texts[index - 1]
        segment = NarrationSegment(
            project_id=project_id,
            text=line,
            sanitized_text=sanitize_text(line),
            position=index,
            service=body.service,
            status="pending",
            magpie_voice=body.magpie_voice,
            original_text=original,
        )
        db.add(segment)
        created_segments.append(segment)

    db.commit()
    for segment in created_segments:
        db.refresh(segment)

    return [_segment_to_dict(segment) for segment in _list_segments(project_id, db)]


@router.post("/api/projects/{project_id}/import-article")
async def api_import_article(
    project_id: uuid.UUID,
    body: ImportArticleRequest,
    db: Session = Depends(get_db),
):
    _get_narration_project_or_404(project_id, db)
    if not body.text.strip():
        raise HTTPException(400, "Article text is empty")

    from app.services.narration.llm import split_article_for_tts_streaming

    async def event_stream():
        async for event in split_article_for_tts_streaming(body.text):
            if event.get("phase") == "done":
                event["service"] = body.service
                event["magpie_voice"] = body.magpie_voice
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/process-chunk")
async def api_process_chunk(body: ProcessChunkRequest):
    if not body.text.strip():
        raise HTTPException(400, "Chunk text is empty")

    from app.services.narration.llm import process_single_chunk

    try:
        segments = await process_single_chunk(body.text)
    except Exception as exc:
        raise HTTPException(502, f"LLM processing failed: {exc}")

    return {"segments": segments}


@router.post("/api/projects/{project_id}/segments/sync")
async def api_sync_segments(
    project_id: uuid.UUID,
    body: SyncRequest,
    db: Session = Depends(get_db),
):
    _get_narration_project_or_404(project_id, db)

    lines = [line for line in body.lines if line.strip()]
    if not lines:
        raise HTTPException(400, "No lines to sync")

    existing = _list_segments(project_id, db)
    changed = 0
    added = 0
    removed = 0
    audio_paths_to_delete: list[str] = []

    for index, line in enumerate(lines):
        position = index + 1
        if index < len(existing):
            segment = existing[index]
            if segment.text.strip() == line.strip():
                segment.position = position
                continue

            if segment.audio_path:
                audio_paths_to_delete.append(segment.audio_path)

            for variant in _list_variants(segment.id, db):
                if variant.audio_path:
                    audio_paths_to_delete.append(variant.audio_path)
                db.delete(variant)

            segment.text = line
            segment.sanitized_text = sanitize_text(line)
            segment.position = position
            segment.status = "pending"
            segment.audio_path = None
            segment.studio_voice_audio_path = None
            segment.studio_voice_status = STUDIO_VOICE_STATUS_NOT_CLEANED
            segment.studio_voice_error_message = None
            segment.studio_voice_cleaned_at = None
            segment.duration_seconds = None
            segment.selected_variant_id = None
            segment.error_message = None
            segment.quality_score = None
            segment.needs_review = False
            segment.is_final = False
            segment.last_generated_at = None
            segment.generation_attempts = 0
            changed += 1
            continue

        new_segment = NarrationSegment(
            project_id=project_id,
            text=line,
            sanitized_text=sanitize_text(line),
            position=position,
            service=body.service,
            status="pending",
        )
        db.add(new_segment)
        added += 1

    if len(lines) < len(existing):
        for segment in existing[len(lines) :]:
            if segment.audio_path:
                audio_paths_to_delete.append(segment.audio_path)
            for variant in _list_variants(segment.id, db):
                if variant.audio_path:
                    audio_paths_to_delete.append(variant.audio_path)
            db.delete(segment)
            removed += 1

    db.commit()

    for path in audio_paths_to_delete:
        _safe_unlink(path)

    return {
        "segments": [
            _segment_to_dict(segment) for segment in _list_segments(project_id, db)
        ],
        "changed": changed,
        "added": added,
        "removed": removed,
    }


@router.delete("/api/projects/{project_id}/segments")
async def api_delete_all_segments(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_narration_project_or_404(project_id, db)

    for path in _collect_project_audio_paths(project_id, db):
        _safe_unlink(path)

    deleted = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.project_id == project_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.get("/api/segments/{segment_id}/audio")
async def api_get_audio(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    audio_path = _resolve_existing_segment_audio_path(segment, db)
    if not audio_path:
        raise HTTPException(404, "Audio not generated yet")
    return FileResponse(audio_path, media_type="audio/wav")


@router.get("/api/segments/{segment_id}/audio/cleaned")
async def api_get_cleaned_audio(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    cleaned_path = _resolve_existing_segment_cleaned_audio_path(segment, db)
    if not cleaned_path:
        raise HTTPException(404, "Studio Voice audio not generated yet")
    return FileResponse(cleaned_path, media_type="audio/wav")


@router.get("/api/segments/{segment_id}/waveform")
async def api_get_segment_waveform(
    segment_id: int,
    points: int = Query(520, ge=64, le=4096),
    source: Literal["original", "cleaned"] = Query("original"),
    db: Session = Depends(get_db),
):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    if source == "cleaned":
        audio_path = _resolve_existing_segment_cleaned_audio_path(segment, db)
    else:
        audio_path = _resolve_existing_segment_audio_path(segment, db)

    if not audio_path:
        raise HTTPException(404, f"{source.title()} audio not available for waveform")

    try:
        samples, duration_ms = _compute_waveform_samples(audio_path, points)
    except Exception as exc:
        raise HTTPException(500, f"Waveform generation failed: {exc}")

    return {
        "segment_id": segment.id,
        "source": source,
        "audio_path": audio_path,
        "points": points,
        "duration_ms": duration_ms,
        "samples": samples,
    }


@router.get("/api/voices")
async def api_list_voices():
    try:
        voices = await list_voices()
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch voices: {exc}")
    return {"voices": voices}


# --- Voice Samples ---


@router.get("/api/voice-samples")
async def api_list_voice_samples(db: Session = Depends(get_db)):
    samples = (
        db.query(NarrationVoiceSample)
        .order_by(NarrationVoiceSample.created_at.asc())
        .all()
    )
    return [_voice_sample_to_dict(sample) for sample in samples]


@router.post("/api/voice-samples/drafts", status_code=201)
async def api_create_voice_sample_draft(clip: UploadFile = File(...)):
    draft = await _create_voice_sample_draft_from_upload(clip, transcribe=True)
    return _voice_sample_draft_to_dict(draft)


@router.get("/api/voice-samples/drafts/{draft_id}")
async def api_get_voice_sample_draft(draft_id: str):
    draft = _get_voice_sample_draft_or_404(draft_id)
    return _voice_sample_draft_to_dict(draft)


@router.get("/api/voice-samples/drafts/{draft_id}/audio")
async def api_get_voice_sample_draft_audio(draft_id: str):
    draft = _get_voice_sample_draft_or_404(draft_id)
    return FileResponse(draft.audio_path, media_type="audio/wav")


@router.post("/api/voice-samples/drafts/{draft_id}/transcribe")
async def api_transcribe_voice_sample_draft(draft_id: str):
    draft = _get_voice_sample_draft_or_404(draft_id)
    text, words = await _transcribe_audio_file_or_502(draft.audio_path)
    draft.transcription = text
    draft.words = words
    return _voice_sample_draft_to_dict(draft)


@router.post("/api/voice-samples/drafts/{draft_id}/trim")
async def api_trim_voice_sample_draft(draft_id: str, body: VoiceSampleDraftTrimRequest):
    draft = _get_voice_sample_draft_or_404(draft_id)

    duration_ms = max(1, int(round(get_wav_duration(draft.audio_path) * 1000)))
    start_ms = max(0, body.start_ms)
    end_ms = min(duration_ms, body.end_ms)

    if end_ms <= start_ms:
        raise HTTPException(400, "Trim end must be greater than trim start")
    if end_ms - start_ms < 50:
        raise HTTPException(400, "Trim range must be at least 50ms")

    trim_audio(draft.audio_path, start_ms, end_ms)
    text, words = await _transcribe_audio_file_or_502(draft.audio_path)
    draft.transcription = text
    draft.words = words
    return _voice_sample_draft_to_dict(draft)


@router.post("/api/voice-samples/drafts/{draft_id}/finalize", status_code=201)
async def api_finalize_voice_sample_draft(
    draft_id: str,
    body: VoiceSampleDraftFinalizeRequest,
    db: Session = Depends(get_db),
):
    draft = _get_voice_sample_draft_or_404(draft_id)

    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Voice sample name is required")

    transcript = body.transcript.strip() or draft.transcription
    destination = _voice_sample_output_path(name)

    VOICE_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(draft.audio_path, destination)

    sample = NarrationVoiceSample(
        name=name,
        audio_path=str(destination),
        transcript=transcript,
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)

    _cleanup_voice_sample_draft(draft_id)
    return _voice_sample_to_dict(sample)


@router.delete("/api/voice-samples/drafts/{draft_id}")
async def api_delete_voice_sample_draft(draft_id: str):
    draft = voice_sample_drafts.get(draft_id)
    if not draft:
        raise HTTPException(404, "Voice sample draft not found")
    _cleanup_voice_sample_draft(draft_id)
    return {"ok": True}


@router.post("/api/voice-samples", status_code=201)
async def api_create_voice_sample(
    name: str = Form(...),
    transcript: str = Form(""),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(400, "Voice sample name is required")

    requested_transcript = transcript.strip()
    draft = await _create_voice_sample_draft_from_upload(
        audio,
        transcribe=not requested_transcript,
    )
    try:
        VOICE_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        destination = _voice_sample_output_path(clean_name)
        shutil.copy2(draft.audio_path, destination)

        sample = NarrationVoiceSample(
            name=clean_name,
            audio_path=str(destination),
            transcript=requested_transcript or draft.transcription,
        )
        db.add(sample)
        db.commit()
        db.refresh(sample)
        return _voice_sample_to_dict(sample)
    finally:
        _cleanup_voice_sample_draft(draft.id)


@router.get("/api/voice-samples/{sample_id}")
async def api_get_voice_sample(sample_id: int, db: Session = Depends(get_db)):
    sample = (
        db.query(NarrationVoiceSample)
        .filter(NarrationVoiceSample.id == sample_id)
        .first()
    )
    if not sample:
        raise HTTPException(404, "Voice sample not found")
    return _voice_sample_to_dict(sample)


@router.patch("/api/voice-samples/{sample_id}")
async def api_update_voice_sample(
    sample_id: int,
    body: VoiceSampleUpdateRequest,
    db: Session = Depends(get_db),
):
    sample = (
        db.query(NarrationVoiceSample)
        .filter(NarrationVoiceSample.id == sample_id)
        .first()
    )
    if not sample:
        raise HTTPException(404, "Voice sample not found")

    sample.transcript = body.transcript.strip()
    db.commit()
    db.refresh(sample)
    return _voice_sample_to_dict(sample)


@router.get("/api/voice-samples/{sample_id}/audio")
async def api_get_voice_sample_audio(sample_id: int, db: Session = Depends(get_db)):
    sample = (
        db.query(NarrationVoiceSample)
        .filter(NarrationVoiceSample.id == sample_id)
        .first()
    )
    if not sample:
        raise HTTPException(404, "Voice sample not found")
    if not sample.audio_path or not os.path.exists(sample.audio_path):
        raise HTTPException(404, "Voice sample audio not found")
    return FileResponse(sample.audio_path, media_type="audio/wav")


@router.delete("/api/voice-samples/{sample_id}")
async def api_delete_voice_sample(sample_id: int, db: Session = Depends(get_db)):
    sample = (
        db.query(NarrationVoiceSample)
        .filter(NarrationVoiceSample.id == sample_id)
        .first()
    )
    if not sample:
        raise HTTPException(404, "Voice sample not found")

    _safe_unlink(sample.audio_path)
    db.delete(sample)
    db.commit()
    return {"ok": True}


# --- Transcriptions ---


async def _transcribe_audio_file(audio_path: str) -> tuple[str, list[dict]]:
    return await transcribe_audio_file(audio_path)


async def _transcribe_audio_file_or_502(audio_path: str) -> tuple[str, list[dict]]:
    try:
        return await _transcribe_audio_file(audio_path)
    except httpx.ConnectError:
        raise HTTPException(
            502,
            f"Could not connect to speech-to-text service at {STT_URL}",
        )
    except Exception as exc:
        raise HTTPException(502, f"Transcription failed: {exc}")


@router.post("/api/segments/{segment_id}/transcribe")
async def api_transcribe_segment(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    audio_path = _resolve_existing_segment_audio_path(segment, db)
    if not audio_path:
        raise HTTPException(400, "Segment has no audio to transcribe")

    text, words = await _transcribe_audio_file_or_502(audio_path)
    transcription = _upsert_transcription(db, segment_id, text, words)

    return _transcription_to_dict(transcription)


@router.get("/api/segments/{segment_id}/transcription")
async def api_get_transcription(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    transcription = (
        db.query(NarrationTranscription)
        .filter(NarrationTranscription.segment_id == segment_id)
        .first()
    )
    if not transcription:
        raise HTTPException(404, "No transcription for this segment")
    return _transcription_to_dict(transcription)


@router.delete("/api/segments/{segment_id}/transcription")
async def api_delete_transcription(segment_id: int, db: Session = Depends(get_db)):
    deleted = (
        db.query(NarrationTranscription)
        .filter(NarrationTranscription.segment_id == segment_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "No transcription to delete")
    return {"ok": True}


@router.post("/api/segments/{segment_id}/trim")
async def api_trim_segment(
    segment_id: int,
    body: TrimRequest,
    db: Session = Depends(get_db),
):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    audio_path = _resolve_existing_segment_audio_path(segment, db)
    if not audio_path:
        raise HTTPException(400, "Segment has no audio to trim")

    duration_ms = max(1, int(round(get_wav_duration(audio_path) * 1000)))
    start_ms = max(0, body.start_ms)
    end_ms = min(duration_ms, body.end_ms)
    trim_mode = body.mode

    if end_ms <= start_ms:
        raise HTTPException(400, "Trim end must be greater than trim start")
    if end_ms - start_ms < 50:
        raise HTTPException(400, "Trim range must be at least 50ms")
    if trim_mode == "remove" and duration_ms - (end_ms - start_ms) < 50:
        raise HTTPException(400, "Trim must leave at least 50ms of audio")

    new_duration = trim_audio(audio_path, start_ms, end_ms, mode=trim_mode)
    rounded_duration = round(new_duration, 2)
    segment.duration_seconds = rounded_duration

    selected_variant = (
        db.query(NarrationVariant)
        .filter(
            NarrationVariant.segment_id == segment_id,
            NarrationVariant.audio_path == audio_path,
        )
        .first()
    )
    if selected_variant:
        selected_variant.duration_seconds = rounded_duration
        _safe_unlink(selected_variant.studio_voice_audio_path)
        selected_variant.studio_voice_audio_path = None
        selected_variant.studio_voice_status = STUDIO_VOICE_STATUS_NOT_CLEANED
        selected_variant.studio_voice_error_message = None
        selected_variant.studio_voice_cleaned_at = None

    _safe_unlink(segment.studio_voice_audio_path)
    segment.studio_voice_audio_path = None
    segment.studio_voice_status = STUDIO_VOICE_STATUS_NOT_CLEANED
    segment.studio_voice_error_message = None
    segment.studio_voice_cleaned_at = None

    db.query(NarrationVariant).filter(
        NarrationVariant.segment_id == segment_id,
        NarrationVariant.audio_path == audio_path,
    ).update(
        {
            NarrationVariant.duration_seconds: rounded_duration,
            NarrationVariant.studio_voice_audio_path: None,
            NarrationVariant.studio_voice_status: STUDIO_VOICE_STATUS_NOT_CLEANED,
            NarrationVariant.studio_voice_error_message: None,
            NarrationVariant.studio_voice_cleaned_at: None,
        },
        synchronize_session=False,
    )

    db.query(NarrationTranscription).filter(
        NarrationTranscription.segment_id == segment_id
    ).delete(synchronize_session=False)
    db.commit()

    transcription_payload = None
    try:
        text, words = await _transcribe_audio_file(audio_path)
        transcription = _upsert_transcription(db, segment_id, text, words)
        transcription_payload = _transcription_to_dict(transcription)
    except Exception as exc:
        logger.warning(
            "Re-transcription after trim failed for segment %s: %s",
            segment_id,
            exc,
        )

    sv_client = build_studio_voice_client(db)
    if sv_client.auto_clean and os.path.exists(audio_path):
        studio_voice_result = await enhance_audio_file(
            audio_path,
            output_audio_path=studio_voice_output_path(audio_path),
            check_health=True,
            client=sv_client,
        )

        segment.studio_voice_audio_path = studio_voice_result.output_path
        segment.studio_voice_status = studio_voice_result.status
        segment.studio_voice_error_message = studio_voice_result.error_message
        segment.studio_voice_cleaned_at = studio_voice_result.cleaned_at

        if selected_variant:
            selected_variant.studio_voice_audio_path = studio_voice_result.output_path
            selected_variant.studio_voice_status = studio_voice_result.status
            selected_variant.studio_voice_error_message = (
                studio_voice_result.error_message
            )
            selected_variant.studio_voice_cleaned_at = studio_voice_result.cleaned_at

        db.query(NarrationVariant).filter(
            NarrationVariant.segment_id == segment_id,
            NarrationVariant.audio_path == audio_path,
        ).update(
            {
                NarrationVariant.studio_voice_audio_path: studio_voice_result.output_path,
                NarrationVariant.studio_voice_status: studio_voice_result.status,
                NarrationVariant.studio_voice_error_message: studio_voice_result.error_message,
                NarrationVariant.studio_voice_cleaned_at: studio_voice_result.cleaned_at,
            },
            synchronize_session=False,
        )
        db.commit()

    db.refresh(segment)
    return {
        "segment": _segment_to_dict(segment),
        "transcription": transcription_payload,
    }


@router.get("/api/projects/{project_id}/transcriptions")
async def api_get_project_transcriptions(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_narration_project_or_404(project_id, db)

    transcriptions = (
        db.query(NarrationTranscription)
        .join(
            NarrationSegment, NarrationTranscription.segment_id == NarrationSegment.id
        )
        .filter(NarrationSegment.project_id == project_id)
        .all()
    )
    return {
        transcription.segment_id: _transcription_to_dict(transcription)
        for transcription in transcriptions
    }


@router.post("/api/projects/{project_id}/transcribe-all", status_code=202)
async def api_transcribe_all(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_narration_project_or_404(project_id, db)

    segments = _list_segments(project_id, db)
    existing = {
        segment_id
        for (segment_id,) in db.query(NarrationTranscription.segment_id)
        .join(
            NarrationSegment, NarrationTranscription.segment_id == NarrationSegment.id
        )
        .filter(NarrationSegment.project_id == project_id)
        .all()
    }

    to_transcribe = [
        segment
        for segment in segments
        if segment.status == "done"
        and segment.audio_path
        and segment.id not in existing
    ]

    if not to_transcribe:
        return {"message": "All segments already transcribed", "transcribed": 0}

    transcribed = 0
    errors = []

    for segment in to_transcribe:
        try:
            text, words = await _transcribe_audio_file(segment.audio_path)
            _upsert_transcription(db, segment.id, text, words)
            transcribed += 1
        except Exception as exc:
            errors.append({"id": segment.id, "error": str(exc)})

    return {"transcribed": transcribed, "errors": errors, "total": len(to_transcribe)}


# --- Generation ---


def _segment_needs_studio_voice_clean(segment: NarrationSegment) -> bool:
    if not segment.audio_path or not os.path.exists(segment.audio_path):
        return False
    if segment.studio_voice_audio_path and os.path.exists(
        segment.studio_voice_audio_path
    ):
        return False
    return True


def _variant_needs_studio_voice_clean(variant: NarrationVariant) -> bool:
    if not variant.audio_path or not os.path.exists(variant.audio_path):
        return False
    if variant.studio_voice_audio_path and os.path.exists(
        variant.studio_voice_audio_path
    ):
        return False
    return True


def _count_project_studio_voice_cleanable_items(
    project_id: uuid.UUID,
    db: Session,
) -> int:
    count = 0
    segments = _list_segments(project_id, db)
    for segment in segments:
        variants = _list_variants(segment.id, db)
        if variants:
            count += sum(
                1 for variant in variants if _variant_needs_studio_voice_clean(variant)
            )
            continue
        if _segment_needs_studio_voice_clean(segment):
            count += 1
    return count


def _enqueue_generation_job(
    *,
    segment_ids: list[int],
    text_overrides: dict[int, str] | None = None,
    review_segment_ids: list[int] | None = None,
    project_id: uuid.UUID | None = None,
) -> GenerationJob:
    job = GenerationJob(
        segment_ids=segment_ids,
        text_overrides=text_overrides or {},
        review_segment_ids=review_segment_ids or [],
        project_id=project_id,
    )
    init_narration_job(job.id, total=len(segment_ids))
    increment_narration_queue_depth(len(segment_ids))

    review_ids = set(job.review_segment_ids)

    for index, segment_id in enumerate(segment_ids):
        text_override = job.text_overrides.get(segment_id)
        kwargs = {
            "segment_id": segment_id,
            "job_id": job.id,
            "index": index,
            "total": len(segment_ids),
            "mark_needs_review": segment_id in review_ids,
        }
        if text_override:
            kwargs["text_override"] = text_override
        generate_narration_segment_task.apply_async(kwargs=kwargs, queue="dia")

    return job


async def _broadcast_job_queued(job: GenerationJob):
    await _broadcast(
        {
            "type": "queued",
            "job_id": job.id,
            "segment_ids": job.segment_ids,
            "position": 0,
        }
    )
    await _broadcast(_queue_status())


@router.post("/api/segments/{segment_id}/generate", status_code=202)
async def api_generate_segment(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    job = _enqueue_generation_job(
        segment_ids=[segment_id],
        project_id=segment.project_id,
    )
    await _broadcast_job_queued(job)
    return {"job_id": job.id, "queued": 1}


@router.post("/api/projects/{project_id}/generate/all", status_code=202)
async def api_generate_all(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_narration_project_or_404(project_id, db)
    segments = _list_segments(project_id, db)
    pending = [segment for segment in segments if segment.status != "done"]
    if not pending:
        return {"message": "All segments already generated", "queued": 0}

    job = _enqueue_generation_job(
        segment_ids=[segment.id for segment in pending],
        project_id=project_id,
    )
    await _broadcast_job_queued(job)
    return {"job_id": job.id, "queued": len(pending)}


@router.post("/api/projects/{project_id}/generate/failed", status_code=202)
async def api_generate_failed(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_narration_project_or_404(project_id, db)
    segments = _list_segments(project_id, db)
    failed_segments = [segment for segment in segments if segment.status == "error"]
    if not failed_segments:
        return {"message": "No failed segments", "queued": 0}

    job = _enqueue_generation_job(
        segment_ids=[segment.id for segment in failed_segments],
        project_id=project_id,
    )
    await _broadcast_job_queued(job)
    return {"job_id": job.id, "queued": len(failed_segments)}


@router.post("/api/projects/{project_id}/studio-voice/clean-all", status_code=202)
async def api_clean_all_with_studio_voice(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_narration_project_or_404(project_id, db)
    cleanable = _count_project_studio_voice_cleanable_items(project_id, db)
    if cleanable == 0:
        return {
            "message": "All eligible audio is already Studio Voice cleaned",
            "queued": 0,
        }

    task = clean_project_studio_voice_task.apply_async(
        kwargs={"project_id": str(project_id)},
        queue="dia",
    )
    return {"task_id": task.id, "queued": cleanable}


@router.post("/api/generation/cancel")
async def api_cancel_generation():
    active_job_id = get_narration_active_job()
    if not active_job_id:
        return {"ok": False, "message": "No active generation job"}

    mark_narration_job_cancelled(active_job_id)
    await _broadcast(
        {
            "type": "job_cancelled",
            "job_id": active_job_id,
            "completed": 0,
            "remaining": 0,
        }
    )
    await _broadcast(_queue_status())
    return {"ok": True, "job_id": active_job_id}


@router.get("/api/status")
async def api_status():
    queue_status = _queue_status()
    queue_length = queue_status.get("queue_length", 0)
    active_job_id = queue_status.get("active_job_id")
    return {
        "active": active_job_id is not None or queue_length > 0,
        "active_job_id": active_job_id,
        "queue_length": queue_length,
    }


@dataclass
class _TimelineExportArtifacts:
    payload: dict
    audio_files: list[tuple[str, str]]
    image_files: list[tuple[str, str]]


def _preferred_export_audio_path(segment: NarrationSegment, db: Session) -> str | None:
    cleaned = _resolve_existing_segment_cleaned_audio_path(segment, db, persist=False)
    if cleaned and os.path.exists(cleaned):
        return cleaned
    original = _resolve_existing_segment_audio_path(segment, db, persist=False)
    if original and os.path.exists(original):
        return original
    return None


def _audio_export_filename(segment: NarrationSegment) -> str:
    return (
        f"{segment.position:03d}_"
        f"{_safe_slug(segment.text[:30] or f'segment_{segment.position}')}.wav"
    )


def _image_export_filename(
    segment: NarrationSegment,
    frame: NarrationImageFrame,
    index: int,
) -> str:
    suffix = Path(frame.output_image_path or "").suffix.lower() or ".png"
    frame_token = _safe_slug(frame.step_key or str(frame.id))
    return f"{segment.position:03d}/" f"{index:03d}_{frame_token}{suffix}"


def _latest_sequence_frames_for_segment(
    segment: NarrationSegment,
) -> tuple[NarrationImageSeries | None, list[NarrationImageFrame]]:
    candidates = sorted(
        segment.image_series,
        key=lambda item: item.completed_at or item.updated_at or item.created_at,
        reverse=True,
    )
    for series in candidates:
        frames = [
            frame
            for frame in sorted(
                series.frames,
                key=lambda item: (item.step_order, item.created_at),
            )
            if frame.status == NarrationImageFrameStatus.COMPLETED.value
            and frame.output_image_path
            and os.path.exists(frame.output_image_path)
        ]
        if frames:
            return series, frames
    return None, []


def _build_timeline_export_artifacts(
    *,
    project: Project,
    db: Session,
    fps: int,
) -> _TimelineExportArtifacts:
    segments = _list_segments(project.id, db)
    done_segments = [segment for segment in segments if segment.status == "done"]

    exported_segments: list[dict] = []
    audio_files: list[tuple[str, str]] = []
    image_files: list[tuple[str, str]] = []

    current_frame = 1
    for segment in done_segments:
        audio_path = _preferred_export_audio_path(segment, db)
        if not audio_path:
            continue

        audio_filename = _audio_export_filename(segment)
        audio_files.append((audio_path, audio_filename))

        duration_seconds = 0.0
        with suppress(Exception):
            duration_seconds = get_wav_duration(audio_path)
        if duration_seconds <= 0:
            duration_seconds = segment.duration_seconds or (1.0 / fps)

        segment_frame_count = max(1, int(round(duration_seconds * fps)))
        segment_start = current_frame
        segment_end_exclusive = segment_start + segment_frame_count

        latest_series, latest_frames = _latest_sequence_frames_for_segment(segment)
        if len(latest_frames) > segment_frame_count:
            latest_frames = latest_frames[:segment_frame_count]

        image_entries: list[dict] = []
        if latest_frames:
            image_count = len(latest_frames)
            for index, frame in enumerate(latest_frames):
                image_start = (
                    segment_start + (index * segment_frame_count) // image_count
                )
                image_end_exclusive = (
                    segment_start + ((index + 1) * segment_frame_count) // image_count
                )
                if index == image_count - 1:
                    image_end_exclusive = segment_end_exclusive
                if image_end_exclusive <= image_start:
                    image_end_exclusive = min(segment_end_exclusive, image_start + 1)
                if image_start >= segment_end_exclusive:
                    break

                image_filename = _image_export_filename(segment, frame, index + 1)
                image_files.append((frame.output_image_path or "", image_filename))
                image_entries.append(
                    {
                        "frame_id": str(frame.id),
                        "step_order": frame.step_order,
                        "step_key": frame.step_key,
                        "filename": image_filename,
                        "start_frame": image_start,
                        "end_frame_exclusive": image_end_exclusive,
                        "frame_count": image_end_exclusive - image_start,
                    }
                )

        exported_segments.append(
            {
                "segment_id": segment.id,
                "position": segment.position,
                "text": segment.text,
                "audio": {
                    "filename": audio_filename,
                    "duration_seconds": round(duration_seconds, 6),
                    "start_frame": segment_start,
                    "end_frame_exclusive": segment_end_exclusive,
                    "frame_count": segment_frame_count,
                },
                "latest_image_series_id": (
                    str(latest_series.id) if latest_series else None
                ),
                "images": image_entries,
            }
        )
        current_frame = segment_end_exclusive

    payload = {
        "project_id": str(project.id),
        "project_name": project.name,
        "fps": fps,
        "audio_channel": 3,
        "image_channel": 4,
        "audio_volume": 1.9,
        "timeline": {
            "start_frame": 1,
            "end_frame_exclusive": current_frame,
        },
        "segments": exported_segments,
    }
    return _TimelineExportArtifacts(
        payload=payload,
        audio_files=audio_files,
        image_files=image_files,
    )


@router.get("/api/projects/{project_id}/export")
async def api_export(
    project_id: uuid.UUID,
    format: str = Query("wav", pattern="^(wav|mp3)$"),
    gap_ms: int = Query(750, ge=0, le=5000),
    fade_ms: int = Query(50, ge=0, le=500),
    normalize: bool = Query(True),
    db: Session = Depends(get_db),
):
    project = _get_narration_project_or_404(project_id, db)
    artifacts = _build_timeline_export_artifacts(project=project, db=db, fps=24)
    if not artifacts.audio_files:
        raise HTTPException(400, "No audio segments to export")

    paths = [path for path, _filename in artifacts.audio_files]
    combined = concatenate_segments(
        paths,
        gap_ms=gap_ms,
        fade_ms=fade_ms,
        normalize=normalize,
    )
    buffer, media_type = export_audio(combined, fmt=format)

    slug = _safe_slug(project.name.replace(" ", "_").lower())
    ext = "mp3" if format == "mp3" else "wav"
    filename = f"narration_{slug}.{ext}"

    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/projects/{project_id}/export-zip")
async def api_export_zip(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    project = _get_narration_project_or_404(project_id, db)
    artifacts = _build_timeline_export_artifacts(project=project, db=db, fps=24)
    if not artifacts.audio_files:
        raise HTTPException(400, "No audio segments to export")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for source_path, filename_in_zip in artifacts.audio_files:
            if source_path and os.path.exists(source_path):
                zip_file.write(source_path, filename_in_zip)

    zip_buffer.seek(0)
    slug = _safe_slug(project.name.replace(" ", "_").lower())
    filename = f"narration_{slug}_segments.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/projects/{project_id}/export-images-zip")
async def api_export_images_zip(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    project = _get_narration_project_or_404(project_id, db)
    artifacts = _build_timeline_export_artifacts(project=project, db=db, fps=24)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for source_path, filename_in_zip in artifacts.image_files:
            if source_path and os.path.exists(source_path):
                zip_file.write(source_path, filename_in_zip)

    zip_buffer.seek(0)
    slug = _safe_slug(project.name.replace(" ", "_").lower())
    filename = f"narration_{slug}_images.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/projects/{project_id}/export-timeline-metadata")
async def api_export_timeline_metadata(
    project_id: uuid.UUID,
    fps: int = Query(24, ge=1, le=120),
    db: Session = Depends(get_db),
):
    project = _get_narration_project_or_404(project_id, db)
    artifacts = _build_timeline_export_artifacts(project=project, db=db, fps=fps)
    if not artifacts.audio_files:
        raise HTTPException(400, "No audio segments to export")
    return artifacts.payload


# --- Variants ---


@router.post("/api/segments/{segment_id}/regenerate", status_code=202)
async def api_regenerate_segment(
    segment_id: int,
    body: RegenerateRequest | None = None,
    db: Session = Depends(get_db),
):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    segment.needs_review = True
    segment.is_final = False
    db.commit()

    text_override = body.text if body else None
    overrides = {segment_id: text_override} if text_override else {}
    job = _enqueue_generation_job(
        segment_ids=[segment_id],
        text_overrides=overrides,
        review_segment_ids=[segment_id],
        project_id=segment.project_id,
    )
    await _broadcast_job_queued(job)
    return {"job_id": job.id, "queued": 1}


@router.get("/api/segments/{segment_id}/variants")
async def api_list_variants(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    variants = _list_variants(segment_id, db)
    return [_variant_to_dict(variant) for variant in variants]


@router.post("/api/segments/{segment_id}/variants/{variant_id}/select")
async def api_select_variant(
    segment_id: int,
    variant_id: int,
    db: Session = Depends(get_db),
):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    variant = (
        db.query(NarrationVariant).filter(NarrationVariant.id == variant_id).first()
    )
    if not variant or variant.segment_id != segment_id:
        raise HTTPException(404, "Variant not found for this segment")

    segment.status = "done"
    segment.audio_path = variant.audio_path
    segment.studio_voice_audio_path = variant.studio_voice_audio_path
    segment.studio_voice_status = variant.studio_voice_status
    segment.studio_voice_error_message = variant.studio_voice_error_message
    segment.studio_voice_cleaned_at = variant.studio_voice_cleaned_at
    segment.duration_seconds = variant.duration_seconds
    segment.selected_variant_id = variant_id
    segment.error_message = None
    segment.needs_review = False
    segment.is_final = False
    db.query(NarrationTranscription).filter(
        NarrationTranscription.segment_id == segment_id
    ).delete(synchronize_session=False)
    db.commit()
    db.refresh(segment)
    return _segment_to_dict(segment)


@router.get("/api/variants/{variant_id}/audio")
async def api_get_variant_audio(variant_id: int, db: Session = Depends(get_db)):
    variant = (
        db.query(NarrationVariant).filter(NarrationVariant.id == variant_id).first()
    )
    if not variant:
        raise HTTPException(404, "Variant not found")
    if not variant.audio_path or not os.path.exists(variant.audio_path):
        raise HTTPException(404, "Variant audio not found")
    return FileResponse(variant.audio_path, media_type="audio/wav")


@router.get("/api/variants/{variant_id}/audio/cleaned")
async def api_get_variant_cleaned_audio(variant_id: int, db: Session = Depends(get_db)):
    variant = (
        db.query(NarrationVariant).filter(NarrationVariant.id == variant_id).first()
    )
    if not variant:
        raise HTTPException(404, "Variant not found")
    if not variant.studio_voice_audio_path or not os.path.exists(
        variant.studio_voice_audio_path
    ):
        raise HTTPException(404, "Variant Studio Voice audio not found")
    return FileResponse(variant.studio_voice_audio_path, media_type="audio/wav")


@router.delete("/api/variants/{variant_id}")
async def api_delete_variant(variant_id: int, db: Session = Depends(get_db)):
    variant = (
        db.query(NarrationVariant).filter(NarrationVariant.id == variant_id).first()
    )
    if not variant:
        raise HTTPException(404, "Variant not found")

    segment = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == variant.segment_id)
        .first()
    )

    if segment and segment.selected_variant_id == variant_id:
        other_variants = [
            candidate
            for candidate in _list_variants(variant.segment_id, db)
            if candidate.id != variant_id
        ]
        if other_variants:
            best = other_variants[0]
            segment.audio_path = best.audio_path
            segment.studio_voice_audio_path = best.studio_voice_audio_path
            segment.studio_voice_status = best.studio_voice_status
            segment.studio_voice_error_message = best.studio_voice_error_message
            segment.studio_voice_cleaned_at = best.studio_voice_cleaned_at
            segment.duration_seconds = best.duration_seconds
            segment.selected_variant_id = best.id
            segment.status = "done"
            segment.error_message = None
            segment.needs_review = False
            segment.is_final = False
        else:
            segment.status = "pending"
            segment.audio_path = None
            segment.studio_voice_audio_path = None
            segment.studio_voice_status = STUDIO_VOICE_STATUS_NOT_CLEANED
            segment.studio_voice_error_message = None
            segment.studio_voice_cleaned_at = None
            segment.duration_seconds = None
            segment.selected_variant_id = None
            segment.error_message = None
            segment.quality_score = None
            segment.needs_review = False
            segment.is_final = False
            segment.last_generated_at = None
            segment.generation_attempts = 0
        db.query(NarrationTranscription).filter(
            NarrationTranscription.segment_id == segment.id
        ).delete(synchronize_session=False)

    _safe_unlink(variant.audio_path)
    _safe_unlink(variant.studio_voice_audio_path)
    db.delete(variant)
    db.commit()
    return {"ok": True}


# --- WebSocket ---


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        await ws.send_text(json.dumps(_queue_status()))
        while True:
            data = await ws.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue
            if message.get("type") == "cancel":
                active_job_id = get_narration_active_job()
                if active_job_id and not is_narration_job_cancelled(active_job_id):
                    mark_narration_job_cancelled(active_job_id)
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)
