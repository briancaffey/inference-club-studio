import asyncio
import json
import logging
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db import (
    init_db,
    list_projects,
    get_project,
    create_project,
    update_project,
    delete_project,
    get_project_audio_paths,
    list_segments,
    get_segment,
    create_segment,
    update_segment,
    delete_segment,
    delete_all_segments,
    reorder_segments,
    shift_segment_positions,
    import_script,
    sync_segments,
    create_variant,
    get_variant,
    list_variants,
    delete_variant,
    list_voice_samples,
    get_voice_sample,
    create_voice_sample,
    delete_voice_sample,
    get_transcription,
    create_transcription,
    delete_transcription,
    get_transcriptions_for_project,
)
from app.services.sanitize import sanitize_text

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
VOICE_SAMPLES_DIR = os.path.join(OUTPUT_DIR, "voice_samples")
STT_URL = os.environ.get("STT_URL", "http://192.168.5.96:8001")


# --- Generation queue infrastructure ---

@dataclass
class GenerationJob:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    segment_ids: list[int] = field(default_factory=list)
    text_overrides: dict[int, str] = field(default_factory=dict)
    project_id: int | None = None

generation_queue: asyncio.Queue[GenerationJob] = asyncio.Queue()
cancel_event: asyncio.Event = asyncio.Event()
active_job: dict = {"job": None}  # mutable container for current job
ws_clients: set[WebSocket] = set()
gen_times: dict[str, list[float]] = {"dia": [], "magpie": []}


async def _broadcast(message: dict):
    """Send JSON to all connected WS clients, discard dead connections."""
    dead = set()
    data = json.dumps(message)
    for ws in ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


def _record_time(service: str, elapsed: float):
    """Append to rolling window (last 20 per service)."""
    times = gen_times.setdefault(service, [])
    times.append(elapsed)
    if len(times) > 20:
        gen_times[service] = times[-20:]


def _estimate_time(service: str) -> float:
    """Return moving average for service, defaults 45s dia / 3s magpie."""
    times = gen_times.get(service, [])
    if times:
        return round(sum(times) / len(times), 1)
    return 45.0 if service == "dia" else 3.0


def _queue_status() -> dict:
    return {
        "type": "queue_status",
        "queue_length": generation_queue.qsize(),
        "active_job_id": active_job["job"].id if active_job["job"] else None,
    }


async def _seed_default_voice_sample():
    """Seed Alice as default voice sample if no samples exist."""
    samples = await list_voice_samples()
    if samples:
        return
    alice_wav = os.path.join("sample", "Alice.wav")
    alice_txt = os.path.join("sample", "text.txt")
    if not os.path.exists(alice_wav):
        return
    transcript = ""
    if os.path.exists(alice_txt):
        with open(alice_txt) as f:
            transcript = f.read().strip()
    # Copy to voice_samples dir
    os.makedirs(VOICE_SAMPLES_DIR, exist_ok=True)
    dest = os.path.join(VOICE_SAMPLES_DIR, "Alice.wav")
    if not os.path.exists(dest):
        shutil.copy2(alice_wav, dest)
    await create_voice_sample("Alice", dest, transcript)
    logger.info("Seeded default voice sample: Alice")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(VOICE_SAMPLES_DIR, exist_ok=True)
    await _seed_default_voice_sample()
    worker_task = asyncio.create_task(_generation_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Narration", lifespan=lifespan)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


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

class ProcessChunkRequest(BaseModel):
    text: str


# --- Routes ---

@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))


# --- Projects ---

@app.get("/api/projects")
async def api_list_projects():
    return await list_projects()

@app.post("/api/projects", status_code=201)
async def api_create_project(body: ProjectCreate):
    return await create_project(body.name, body.description)

@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: int):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj

@app.put("/api/projects/{project_id}")
async def api_update_project(project_id: int, body: ProjectUpdate):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    kwargs = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.description is not None:
        kwargs["description"] = body.description
    return await update_project(project_id, **kwargs)

@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: int):
    # Delete audio files first
    paths = await get_project_audio_paths(project_id)
    for p in paths:
        if p and os.path.exists(p):
            os.remove(p)
    # Remove project output dir
    proj_dir = os.path.join(OUTPUT_DIR, str(project_id))
    if os.path.isdir(proj_dir):
        shutil.rmtree(proj_dir)
    ok = await delete_project(project_id)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"ok": True}


# --- Segments (scoped to project) ---

@app.get("/api/projects/{project_id}/segments")
async def api_list_segments(project_id: int):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return await list_segments(project_id)

@app.post("/api/projects/{project_id}/segments", status_code=201)
async def api_create_segment(project_id: int, body: SegmentCreate):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    sanitized = sanitize_text(body.text)
    position = body.position
    if position is None:
        segments = await list_segments(project_id)
        position = len(segments) + 1
    else:
        # Shift existing segments at this position and after to make room
        await shift_segment_positions(project_id, position)
    return await create_segment(project_id, body.text, sanitized, position, body.service, body.voice_sample_id, body.magpie_voice)

@app.put("/api/segments/{segment_id}")
async def api_update_segment(segment_id: int, body: SegmentUpdate):
    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    kwargs = {}
    if body.text is not None:
        kwargs["text"] = body.text
        kwargs["sanitized_text"] = sanitize_text(body.text)
        kwargs["status"] = "pending"
        kwargs["audio_path"] = None
        kwargs["duration_seconds"] = None
    if body.position is not None:
        kwargs["position"] = body.position
    if body.service is not None:
        kwargs["service"] = body.service
    if body.voice_sample_id is not None:
        kwargs["voice_sample_id"] = body.voice_sample_id if body.voice_sample_id > 0 else None
    if body.magpie_voice is not None:
        kwargs["magpie_voice"] = body.magpie_voice if body.magpie_voice else None
    return await update_segment(segment_id, **kwargs)

@app.delete("/api/segments/{segment_id}")
async def api_delete_segment(segment_id: int):
    seg = await get_segment(segment_id)
    if seg and seg["audio_path"] and os.path.exists(seg["audio_path"]):
        os.remove(seg["audio_path"])
    ok = await delete_segment(segment_id)
    if not ok:
        raise HTTPException(404, "Segment not found")
    return {"ok": True}

@app.post("/api/segments/reorder")
async def api_reorder_segments(body: ReorderRequest):
    await reorder_segments([item.model_dump() for item in body.ordering])
    # Return segments for the project of the first item
    if body.ordering:
        seg = await get_segment(body.ordering[0].id)
        if seg:
            return await list_segments(seg["project_id"])
    return []

@app.post("/api/projects/{project_id}/segments/import")
async def api_import_segments(project_id: int, body: ImportRequest):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    lines = [line.strip() for line in body.text.splitlines() if line.strip()]
    if not lines:
        raise HTTPException(400, "No lines to import")
    return await import_script(project_id, lines, body.service, body.magpie_voice, body.original_texts)

@app.post("/api/projects/{project_id}/import-article")
async def api_import_article(project_id: int, body: ImportArticleRequest):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    if not body.text.strip():
        raise HTTPException(400, "Article text is empty")
    from app.services.llm import split_article_for_tts_streaming

    async def event_stream():
        async for event in split_article_for_tts_streaming(body.text):
            if event["phase"] == "done":
                event["service"] = body.service
                event["magpie_voice"] = body.magpie_voice
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/api/process-chunk")
async def api_process_chunk(body: ProcessChunkRequest):
    """Process a single text chunk through the LLM for TTS cleanup."""
    if not body.text.strip():
        raise HTTPException(400, "Chunk text is empty")
    from app.services.llm import process_single_chunk
    try:
        segments = await process_single_chunk(body.text)
        return {"segments": segments}
    except Exception as e:
        raise HTTPException(502, f"LLM processing failed: {e}")

@app.post("/api/projects/{project_id}/segments/sync")
async def api_sync_segments(project_id: int, body: SyncRequest):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    lines = [line for line in body.lines if line.strip()]
    if not lines:
        raise HTTPException(400, "No lines to sync")
    result = await sync_segments(project_id, lines, body.service)
    # Clean up audio files for deleted/changed segments
    for p in result.pop("audio_paths_to_delete", []):
        if p and os.path.exists(p):
            os.remove(p)
    return result

@app.delete("/api/projects/{project_id}/segments")
async def api_delete_all_segments(project_id: int):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    # Delete audio files
    paths = await get_project_audio_paths(project_id)
    for p in paths:
        if p and os.path.exists(p):
            os.remove(p)
    count = await delete_all_segments(project_id)
    return {"ok": True, "deleted": count}

@app.get("/api/segments/{segment_id}/audio")
async def api_get_audio(segment_id: int):
    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    if not seg["audio_path"] or not os.path.exists(seg["audio_path"]):
        raise HTTPException(404, "Audio not generated yet")
    return FileResponse(seg["audio_path"], media_type="audio/wav")

@app.get("/api/voices")
async def api_list_voices():
    from app.services.magpie import list_voices
    try:
        voices = await list_voices()
        return {"voices": voices}
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch voices: {e}")


# --- Voice Samples ---

@app.get("/api/voice-samples")
async def api_list_voice_samples():
    return await list_voice_samples()

@app.post("/api/voice-samples", status_code=201)
async def api_create_voice_sample(
    name: str = Form(...),
    transcript: str = Form(""),
    audio: UploadFile = File(...),
):
    if not audio.filename.lower().endswith(".wav"):
        raise HTTPException(400, "Only WAV files are supported")
    os.makedirs(VOICE_SAMPLES_DIR, exist_ok=True)
    # Save with unique name to avoid collisions
    safe_name = re.sub(r"[^\w\-.]", "_", audio.filename)
    dest = os.path.join(VOICE_SAMPLES_DIR, f"{name.replace(' ', '_').lower()}_{safe_name}")
    content = await audio.read()
    with open(dest, "wb") as f:
        f.write(content)
    return await create_voice_sample(name, dest, transcript)

@app.get("/api/voice-samples/{sample_id}")
async def api_get_voice_sample(sample_id: int):
    vs = await get_voice_sample(sample_id)
    if not vs:
        raise HTTPException(404, "Voice sample not found")
    return vs

@app.get("/api/voice-samples/{sample_id}/audio")
async def api_get_voice_sample_audio(sample_id: int):
    vs = await get_voice_sample(sample_id)
    if not vs:
        raise HTTPException(404, "Voice sample not found")
    if not vs["audio_path"] or not os.path.exists(vs["audio_path"]):
        raise HTTPException(404, "Voice sample audio not found")
    return FileResponse(vs["audio_path"], media_type="audio/wav")

@app.delete("/api/voice-samples/{sample_id}")
async def api_delete_voice_sample(sample_id: int):
    vs = await get_voice_sample(sample_id)
    if not vs:
        raise HTTPException(404, "Voice sample not found")
    if vs["audio_path"] and os.path.exists(vs["audio_path"]):
        os.remove(vs["audio_path"])
    ok = await delete_voice_sample(sample_id)
    if not ok:
        raise HTTPException(404, "Voice sample not found")
    return {"ok": True}


# --- Transcriptions ---

@app.post("/api/segments/{segment_id}/transcribe")
async def api_transcribe_segment(segment_id: int):
    import httpx
    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    if not seg["audio_path"] or not os.path.exists(seg["audio_path"]):
        raise HTTPException(400, "Segment has no audio to transcribe")
    try:
        with open(seg["audio_path"], "rb") as f:
            audio_bytes = f.read()
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10)) as client:
            resp = await client.post(
                f"{STT_URL}/transcribe",
                params={"timestamps": "true"},
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            )
        if resp.status_code != 200:
            raise RuntimeError(f"STT service returned {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        text = data.get("text", "")
        words = data.get("words", [])
        result = await create_transcription(segment_id, text, words)
        return result
    except httpx.ConnectError:
        raise HTTPException(502, f"Could not connect to speech-to-text service at {STT_URL}")
    except Exception as e:
        raise HTTPException(502, f"Transcription failed: {e}")


@app.get("/api/segments/{segment_id}/transcription")
async def api_get_transcription(segment_id: int):
    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    t = await get_transcription(segment_id)
    if not t:
        raise HTTPException(404, "No transcription for this segment")
    return t


@app.delete("/api/segments/{segment_id}/transcription")
async def api_delete_transcription(segment_id: int):
    ok = await delete_transcription(segment_id)
    if not ok:
        raise HTTPException(404, "No transcription to delete")
    return {"ok": True}


@app.post("/api/segments/{segment_id}/trim")
async def api_trim_segment(segment_id: int, body: TrimRequest):
    import httpx
    from app.services.audio import trim_audio

    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    if not seg["audio_path"] or not os.path.exists(seg["audio_path"]):
        raise HTTPException(400, "Segment has no audio to trim")

    new_duration = trim_audio(seg["audio_path"], body.start_ms, body.end_ms)
    await update_segment(segment_id, duration_seconds=round(new_duration, 2))

    # Delete old transcription and re-run STT
    await delete_transcription(segment_id)

    transcription = None
    try:
        with open(seg["audio_path"], "rb") as f:
            audio_bytes = f.read()
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10)) as client:
            resp = await client.post(
                f"{STT_URL}/transcribe",
                params={"timestamps": "true"},
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            )
        if resp.status_code == 200:
            data = resp.json()
            transcription = await create_transcription(segment_id, data.get("text", ""), data.get("words", []))
    except Exception as e:
        logger.warning(f"Re-transcription after trim failed for segment {segment_id}: {e}")

    updated_seg = await get_segment(segment_id)
    return {"segment": updated_seg, "transcription": transcription}


@app.get("/api/projects/{project_id}/transcriptions")
async def api_get_project_transcriptions(project_id: int):
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return await get_transcriptions_for_project(project_id)


@app.post("/api/projects/{project_id}/transcribe-all", status_code=202)
async def api_transcribe_all(project_id: int):
    """Transcribe all segments with audio that don't have transcriptions yet."""
    import httpx
    proj = await get_project(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    segs = await list_segments(project_id)
    existing = await get_transcriptions_for_project(project_id)
    to_transcribe = [s for s in segs if s["status"] == "done" and s["audio_path"] and s["id"] not in existing]
    if not to_transcribe:
        return {"message": "All segments already transcribed", "transcribed": 0}

    transcribed = 0
    errors = []
    for seg in to_transcribe:
        try:
            with open(seg["audio_path"], "rb") as f:
                audio_bytes = f.read()
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10)) as client:
                resp = await client.post(
                    f"{STT_URL}/transcribe",
                    params={"timestamps": "true"},
                    files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                )
            if resp.status_code != 200:
                errors.append({"id": seg["id"], "error": f"HTTP {resp.status_code}"})
                continue
            data = resp.json()
            await create_transcription(seg["id"], data.get("text", ""), data.get("words", []))
            transcribed += 1
        except Exception as e:
            errors.append({"id": seg["id"], "error": str(e)})

    return {"transcribed": transcribed, "errors": errors, "total": len(to_transcribe)}


# --- Generation ---

def _make_output_filename(position: int, text: str, variant_num: int = 0) -> str:
    clean = re.sub(r"\[S\d+\]\s*", "", text)
    words = clean.split()[:5]
    name = "_".join(words)
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name).lower()[:50]
    suffix = f"_v{variant_num}" if variant_num > 0 else ""
    return f"{position:03d}_{name}{suffix}.wav"


async def _generation_worker():
    """Background worker that pulls jobs from the queue and processes them."""
    while True:
        job = await generation_queue.get()
        active_job["job"] = job
        cancel_event.clear()
        generated = 0
        failed = 0
        errors = []
        total = len(job.segment_ids)

        await _broadcast({"type": "queued", "job_id": job.id, "segment_ids": job.segment_ids, "position": 0})
        await _broadcast(_queue_status())

        for i, seg_id in enumerate(job.segment_ids):
            if cancel_event.is_set():
                await _broadcast({
                    "type": "job_cancelled",
                    "job_id": job.id,
                    "completed": i,
                    "remaining": total - i,
                })
                break

            seg = await get_segment(seg_id)
            service = seg["service"] if seg else "dia"
            estimate = _estimate_time(service)

            await _broadcast({
                "type": "segment_start",
                "job_id": job.id,
                "segment_id": seg_id,
                "index": i,
                "total": total,
                "estimate_seconds": estimate,
            })

            t0 = time.monotonic()
            try:
                text_override = job.text_overrides.get(seg_id)
                await _generate_segment(seg_id, text_override=text_override)
                elapsed = round(time.monotonic() - t0, 1)
                _record_time(service, elapsed)
                generated += 1

                seg = await get_segment(seg_id)
                await _broadcast({
                    "type": "segment_done",
                    "job_id": job.id,
                    "segment_id": seg_id,
                    "segment": seg,
                    "index": i,
                    "total": total,
                    "generation_seconds": elapsed,
                })
            except Exception as e:
                elapsed = round(time.monotonic() - t0, 1)
                failed += 1
                errors.append({"id": seg_id, "error": str(e)})
                await _broadcast({
                    "type": "segment_error",
                    "job_id": job.id,
                    "segment_id": seg_id,
                    "error": str(e),
                    "index": i,
                    "total": total,
                })

        if not cancel_event.is_set():
            await _broadcast({
                "type": "job_done",
                "job_id": job.id,
                "generated": generated,
                "failed": failed,
                "errors": errors,
            })

        active_job["job"] = None
        generation_queue.task_done()
        await _broadcast(_queue_status())


async def _generate_segment(segment_id: int, text_override: str | None = None):
    """Generate audio for a single segment."""
    from app.services.dia import generate as dia_generate
    from app.services.dia import get_wav_duration

    seg = await get_segment(segment_id)
    if not seg:
        raise RuntimeError(f"Segment {segment_id} not found")

    await update_segment(segment_id, status="generating")

    if text_override:
        gen_text = sanitize_text(text_override)
        raw_text = text_override
    else:
        gen_text = seg["sanitized_text"]
        raw_text = seg["text"]

    existing_variants = await list_variants(segment_id)
    variant_num = len(existing_variants)

    # Output into project subdirectory
    proj_dir = os.path.join(OUTPUT_DIR, str(seg["project_id"]))
    os.makedirs(proj_dir, exist_ok=True)
    filename = _make_output_filename(seg["position"], raw_text, variant_num)
    output_path = os.path.join(proj_dir, filename)

    try:
        if seg["service"] == "dia":
            # Look up voice sample for custom reference audio/text
            dia_kwargs = {}
            if seg.get("voice_sample_id"):
                vs = await get_voice_sample(seg["voice_sample_id"])
                if vs:
                    dia_kwargs["reference_audio_path"] = vs["audio_path"]
                    if vs["transcript"]:
                        dia_kwargs["reference_text_override"] = vs["transcript"]
            await dia_generate(gen_text, output_path, **dia_kwargs)
        elif seg["service"] == "magpie":
            from app.services.magpie import generate as magpie_generate
            magpie_voice = seg.get("magpie_voice") or None
            await magpie_generate(gen_text, output_path, voice=magpie_voice)
        else:
            raise RuntimeError(f"Unknown service: {seg['service']}")

        duration = get_wav_duration(output_path)

        variant = await create_variant(
            segment_id=segment_id,
            text=raw_text,
            sanitized_text=gen_text,
            service=seg["service"],
            audio_path=output_path,
            duration_seconds=round(duration, 2),
        )

        await update_segment(
            segment_id,
            status="done",
            audio_path=output_path,
            duration_seconds=round(duration, 2),
            error_message=None,
            selected_variant_id=variant["id"],
        )
        logger.info(f"Segment {segment_id} done: {duration:.1f}s (variant {variant['id']})")
    except Exception as e:
        logger.error(f"Segment {segment_id} failed: {e}")
        await update_segment(segment_id, status="error", error_message=str(e))
        raise


@app.post("/api/segments/{segment_id}/generate", status_code=202)
async def api_generate_segment(segment_id: int):
    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    job = GenerationJob(segment_ids=[segment_id], project_id=seg["project_id"])
    await generation_queue.put(job)
    return {"job_id": job.id, "queued": 1}


@app.post("/api/projects/{project_id}/generate/all", status_code=202)
async def api_generate_all(project_id: int):
    segs = await list_segments(project_id)
    pending = [s for s in segs if s["status"] != "done"]
    if not pending:
        return {"message": "All segments already generated", "queued": 0}
    job = GenerationJob(segment_ids=[s["id"] for s in pending], project_id=project_id)
    await generation_queue.put(job)
    return {"job_id": job.id, "queued": len(pending)}


@app.post("/api/projects/{project_id}/generate/failed", status_code=202)
async def api_generate_failed(project_id: int):
    segs = await list_segments(project_id)
    error_segs = [s for s in segs if s["status"] == "error"]
    if not error_segs:
        return {"message": "No failed segments", "queued": 0}
    job = GenerationJob(segment_ids=[s["id"] for s in error_segs], project_id=project_id)
    await generation_queue.put(job)
    return {"job_id": job.id, "queued": len(error_segs)}


@app.post("/api/generation/cancel")
async def api_cancel_generation():
    cancel_event.set()
    return {"ok": True}


@app.get("/api/status")
async def api_status():
    return {
        "active": active_job["job"] is not None,
        "active_job_id": active_job["job"].id if active_job["job"] else None,
        "queue_length": generation_queue.qsize(),
    }


@app.get("/api/projects/{project_id}/export")
async def api_export(
    project_id: int,
    format: str = Query("wav", pattern="^(wav|mp3)$"),
    gap_ms: int = Query(750, ge=0, le=5000),
    fade_ms: int = Query(50, ge=0, le=500),
    normalize: bool = Query(True),
):
    from app.services.audio import concatenate_segments, export_audio

    segments = await list_segments(project_id)
    done = [s for s in segments if s["status"] == "done" and s["audio_path"] and os.path.exists(s["audio_path"])]
    if not done:
        raise HTTPException(400, "No audio segments to export")

    paths = [s["audio_path"] for s in done]
    combined = concatenate_segments(paths, gap_ms=gap_ms, fade_ms=fade_ms, normalize=normalize)
    buf, media_type = export_audio(combined, fmt=format)

    proj = await get_project(project_id)
    name_slug = proj["name"].replace(" ", "_").lower() if proj else "export"
    ext = "mp3" if format == "mp3" else "wav"
    filename = f"narration_{name_slug}.{ext}"

    return StreamingResponse(
        buf,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --- Variants ---

@app.post("/api/segments/{segment_id}/regenerate", status_code=202)
async def api_regenerate_segment(segment_id: int, body: RegenerateRequest | None = None):
    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    text_override = body.text if body else None
    overrides = {segment_id: text_override} if text_override else {}
    job = GenerationJob(segment_ids=[segment_id], text_overrides=overrides, project_id=seg["project_id"])
    await generation_queue.put(job)
    return {"job_id": job.id, "queued": 1}

@app.get("/api/segments/{segment_id}/variants")
async def api_list_variants(segment_id: int):
    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    return await list_variants(segment_id)

@app.post("/api/segments/{segment_id}/variants/{variant_id}/select")
async def api_select_variant(segment_id: int, variant_id: int):
    seg = await get_segment(segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    variant = await get_variant(variant_id)
    if not variant or variant["segment_id"] != segment_id:
        raise HTTPException(404, "Variant not found for this segment")
    await update_segment(
        segment_id,
        status="done",
        audio_path=variant["audio_path"],
        duration_seconds=variant["duration_seconds"],
        selected_variant_id=variant_id,
    )
    return await get_segment(segment_id)

@app.get("/api/variants/{variant_id}/audio")
async def api_get_variant_audio(variant_id: int):
    variant = await get_variant(variant_id)
    if not variant:
        raise HTTPException(404, "Variant not found")
    if not variant["audio_path"] or not os.path.exists(variant["audio_path"]):
        raise HTTPException(404, "Variant audio not found")
    return FileResponse(variant["audio_path"], media_type="audio/wav")

@app.delete("/api/variants/{variant_id}")
async def api_delete_variant(variant_id: int):
    variant = await get_variant(variant_id)
    if not variant:
        raise HTTPException(404, "Variant not found")
    seg = await get_segment(variant["segment_id"])
    if seg and seg.get("selected_variant_id") == variant_id:
        others = [v for v in await list_variants(variant["segment_id"]) if v["id"] != variant_id]
        if others:
            best = others[0]
            await update_segment(
                variant["segment_id"],
                audio_path=best["audio_path"],
                duration_seconds=best["duration_seconds"],
                selected_variant_id=best["id"],
            )
        else:
            await update_segment(
                variant["segment_id"],
                status="pending",
                audio_path=None,
                duration_seconds=None,
                selected_variant_id=None,
            )
    if variant["audio_path"] and os.path.exists(variant["audio_path"]):
        os.remove(variant["audio_path"])
    await delete_variant(variant_id)
    return {"ok": True}


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        await ws.send_text(json.dumps(_queue_status()))
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "cancel":
                    cancel_event.set()
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)
