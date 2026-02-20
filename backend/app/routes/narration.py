import asyncio
import json
import logging
import os
import re
import shutil
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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
from pydantic import BaseModel
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
from app.models.project import Project, ProjectType
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
from app.tasks.narration import generate_narration_segment_task

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
        "duration_seconds": segment.duration_seconds,
        "error_message": segment.error_message,
        "quality_score": segment.quality_score,
        "needs_review": segment.needs_review,
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


def _collect_project_audio_paths(project_id: uuid.UUID, db: Session) -> list[str]:
    segment_paths = (
        db.query(NarrationSegment.audio_path)
        .filter(
            NarrationSegment.project_id == project_id,
            NarrationSegment.audio_path.isnot(None),
        )
        .all()
    )
    variant_paths = (
        db.query(NarrationVariant.audio_path)
        .join(NarrationSegment, NarrationVariant.segment_id == NarrationSegment.id)
        .filter(
            NarrationSegment.project_id == project_id,
            NarrationVariant.audio_path.isnot(None),
        )
        .all()
    )
    return [p for (p,) in (segment_paths + variant_paths) if p]


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
        segment.duration_seconds = None
        segment.error_message = None
        segment.quality_score = None
        segment.needs_review = False
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


@router.delete("/api/segments/{segment_id}")
async def api_delete_segment(segment_id: int, db: Session = Depends(get_db)):
    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == segment_id).first()
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    _safe_unlink(segment.audio_path)

    variants = _list_variants(segment_id, db)
    for variant in variants:
        _safe_unlink(variant.audio_path)

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
            segment.duration_seconds = None
            segment.selected_variant_id = None
            segment.error_message = None
            segment.quality_score = None
            segment.needs_review = False
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
    if not segment.audio_path or not os.path.exists(segment.audio_path):
        raise HTTPException(404, "Audio not generated yet")
    return FileResponse(segment.audio_path, media_type="audio/wav")


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
    if not segment.audio_path or not os.path.exists(segment.audio_path):
        raise HTTPException(400, "Segment has no audio to transcribe")

    text, words = await _transcribe_audio_file_or_502(segment.audio_path)
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
    if not segment.audio_path or not os.path.exists(segment.audio_path):
        raise HTTPException(400, "Segment has no audio to trim")

    duration_ms = max(1, int(round(get_wav_duration(segment.audio_path) * 1000)))
    start_ms = max(0, body.start_ms)
    end_ms = min(duration_ms, body.end_ms)

    if end_ms <= start_ms:
        raise HTTPException(400, "Trim end must be greater than trim start")
    if end_ms - start_ms < 50:
        raise HTTPException(400, "Trim range must be at least 50ms")

    new_duration = trim_audio(segment.audio_path, start_ms, end_ms)
    rounded_duration = round(new_duration, 2)
    segment.duration_seconds = rounded_duration

    db.query(NarrationVariant).filter(
        NarrationVariant.segment_id == segment_id,
        NarrationVariant.audio_path == segment.audio_path,
    ).update(
        {NarrationVariant.duration_seconds: rounded_duration},
        synchronize_session=False,
    )

    db.query(NarrationTranscription).filter(
        NarrationTranscription.segment_id == segment_id
    ).delete(synchronize_session=False)
    db.commit()

    transcription_payload = None
    try:
        text, words = await _transcribe_audio_file(segment.audio_path)
        transcription = _upsert_transcription(db, segment_id, text, words)
        transcription_payload = _transcription_to_dict(transcription)
    except Exception as exc:
        logger.warning(
            "Re-transcription after trim failed for segment %s: %s",
            segment_id,
            exc,
        )

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


def _enqueue_generation_job(
    *,
    segment_ids: list[int],
    text_overrides: dict[int, str] | None = None,
    project_id: uuid.UUID | None = None,
) -> GenerationJob:
    job = GenerationJob(
        segment_ids=segment_ids,
        text_overrides=text_overrides or {},
        project_id=project_id,
    )
    init_narration_job(job.id, total=len(segment_ids))
    increment_narration_queue_depth(len(segment_ids))

    for index, segment_id in enumerate(segment_ids):
        text_override = job.text_overrides.get(segment_id)
        kwargs = {
            "segment_id": segment_id,
            "job_id": job.id,
            "index": index,
            "total": len(segment_ids),
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
    segments = _list_segments(project_id, db)

    done_segments = [
        segment
        for segment in segments
        if segment.status == "done"
        and segment.audio_path
        and os.path.exists(segment.audio_path)
    ]
    if not done_segments:
        raise HTTPException(400, "No audio segments to export")

    paths = [segment.audio_path for segment in done_segments]
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

    text_override = body.text if body else None
    overrides = {segment_id: text_override} if text_override else {}
    job = _enqueue_generation_job(
        segment_ids=[segment_id],
        text_overrides=overrides,
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
    segment.duration_seconds = variant.duration_seconds
    segment.selected_variant_id = variant_id
    segment.error_message = None
    segment.needs_review = False
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
            segment.duration_seconds = best.duration_seconds
            segment.selected_variant_id = best.id
            segment.status = "done"
            segment.error_message = None
            segment.needs_review = False
        else:
            segment.status = "pending"
            segment.audio_path = None
            segment.duration_seconds = None
            segment.selected_variant_id = None
            segment.error_message = None
            segment.quality_score = None
            segment.needs_review = False
            segment.generation_attempts = 0
        db.query(NarrationTranscription).filter(
            NarrationTranscription.segment_id == segment.id
        ).delete(synchronize_session=False)

    _safe_unlink(variant.audio_path)
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
