"""Speech-to-text helper for narration audio files.

Supports two providers, selected via the ``stt`` service config:
  - ``nemotron``: NVIDIA Nemotron NIM custom ``/transcribe`` endpoint
  - ``openai``:   OpenAI-compatible ``/v1/audio/transcriptions`` endpoint
                  (Qwen3-ASR, OpenAI Whisper, vLLM-served Whisper, etc.)

Both return a ``(text, words)`` tuple where ``words`` is a list of dicts
with ``word``, ``start``, ``end`` keys (start/end in seconds) — the
same shape the frontend timeline already consumes.

For the openai provider, if the server only returns plain ``{"text": ...}``
(as Qwen3-ASR does — it rejects ``verbose_json``), we synthesize uniform
per-word timestamps from the audio duration so the timeline UI keeps
working. When the server returns a real ``words`` array (Whisper with
``verbose_json``), we use those directly.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from pydub import AudioSegment

from app.config import settings
from app.database import SessionLocal
from app.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


def _load_stt_config() -> dict:
    """Read the active stt config from the DB, with env fallback."""
    db = SessionLocal()
    try:
        return ConfigManager(db).get_config("stt") or {}
    finally:
        db.close()


def _audio_mime(audio_path: str) -> str:
    suffix = Path(audio_path).suffix.lower().lstrip(".")
    mime_map = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "mp4": "audio/mp4",
        "flac": "audio/flac",
        "ogg": "audio/ogg",
        "webm": "audio/webm",
    }
    return mime_map.get(suffix, "audio/wav")


def _normalize_openai_base_url(raw: str) -> str:
    """Ensure the OpenAI-compatible STT base URL ends in '/v1'.

    Accepts both 'http://host:port' and 'http://host:port/v1'. Trailing
    slashes are stripped. We then always append '/v1' so the caller can
    just do f'{base}/audio/transcriptions' uniformly.
    """
    base = (raw or "").strip().rstrip("/")
    if not base:
        return base
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _audio_duration_seconds(audio_path: str) -> float:
    """Best-effort duration in seconds for a local audio file."""
    try:
        return AudioSegment.from_file(audio_path).duration_seconds
    except Exception as exc:
        logger.warning("Could not read audio duration for %s: %s", audio_path, exc)
        return 0.0


def _synthesize_word_timestamps(text: str, duration: float) -> list[dict]:
    """Distribute words uniformly across ``duration`` seconds.

    Used as a fallback when the STT server returns plain text (no
    timestamps). It's approximate — every word gets the same slice — but
    keeps the timeline / trim UI functional.
    """
    tokens = text.split()
    if not tokens or duration <= 0:
        return []
    slice_s = duration / len(tokens)
    return [
        {
            "word": tok,
            "start": round(i * slice_s, 3),
            "end": round((i + 1) * slice_s, 3),
        }
        for i, tok in enumerate(tokens)
    ]


def _parse_word_list(raw: object) -> list[dict]:
    """Normalize an OpenAI-shaped 'words' array into our timeline shape."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        word_text = entry.get("word") or entry.get("text") or ""
        try:
            start = float(entry.get("start", 0.0))
            end = float(entry.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        out.append({"word": word_text, "start": start, "end": end})
    return out


async def _transcribe_nemotron(audio_path: str, cfg: dict) -> tuple[str, list[dict]]:
    base_url = (cfg.get("base_url") or settings.stt_url).rstrip("/")
    timeout_s = float(cfg.get("timeout", 120.0))

    with open(audio_path, "rb") as source:
        audio_bytes = source.read()

    timeout = httpx.Timeout(connect=10, read=timeout_s, write=10, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/transcribe",
            params={"timestamps": "true"},
            files={
                "file": (
                    os.path.basename(audio_path) or "audio.wav",
                    audio_bytes,
                    _audio_mime(audio_path),
                )
            },
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"STT (nemotron) returned {response.status_code}: {response.text[:300]}"
        )

    payload = response.json()
    return payload.get("text", ""), payload.get("words", [])


async def _transcribe_openai(audio_path: str, cfg: dict) -> tuple[str, list[dict]]:
    base_url = _normalize_openai_base_url(cfg.get("base_url") or "")
    if not base_url:
        raise RuntimeError("STT provider=openai but base_url is not configured")
    model = cfg.get("model") or "whisper-1"
    api_key = cfg.get("api_key") or None
    language = cfg.get("language") or None
    timeout_s = float(cfg.get("timeout", 120.0))

    with open(audio_path, "rb") as source:
        audio_bytes = source.read()

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    files = {
        "file": (
            os.path.basename(audio_path) or "audio.wav",
            audio_bytes,
            _audio_mime(audio_path),
        ),
    }
    # Default to the OpenAI-spec 'json' response, which Qwen3-ASR supports
    # (it explicitly rejects 'verbose_json'). When the server happens to
    # return a 'words' array anyway (e.g. some Whisper deployments), we use
    # it; otherwise we synthesize per-word timestamps below.
    data: dict[str, str] = {
        "model": model,
        "response_format": "json",
    }
    if language:
        data["language"] = language

    timeout = httpx.Timeout(connect=10, read=timeout_s, write=10, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/audio/transcriptions",
            data=data,
            files=files,
            headers=headers,
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"STT (openai) returned {response.status_code}: {response.text[:300]}"
        )

    payload = response.json()
    text = (payload.get("text") or "").strip()
    words = _parse_word_list(payload.get("words"))

    if not words and text:
        usage = payload.get("usage") or {}
        duration = 0.0
        try:
            usage_seconds = usage.get("seconds")
            if usage_seconds is not None:
                duration = float(usage_seconds)
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= 0:
            duration = _audio_duration_seconds(audio_path)
        words = _synthesize_word_timestamps(text, duration)

    return text, words


async def transcribe_audio_file(audio_path: str) -> tuple[str, list[dict]]:
    cfg = _load_stt_config()
    provider = (cfg.get("provider") or "nemotron").lower()

    if provider == "openai":
        return await _transcribe_openai(audio_path, cfg)
    if provider == "nemotron":
        return await _transcribe_nemotron(audio_path, cfg)
    raise RuntimeError(f"Unknown STT provider: {provider}")
