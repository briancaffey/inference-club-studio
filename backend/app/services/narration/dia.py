"""Dia TTS client via Gradio HTTP API with voice cloning."""

import json
import logging
import os
import re
import wave
from pathlib import Path

import httpx

from app.config import settings
from app.database import SessionLocal
from app.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

_sample_dir = Path(__file__).resolve().parent / "sample"
REFERENCE_AUDIO = os.environ.get("REFERENCE_AUDIO", str(_sample_dir / "Alice.wav"))
REFERENCE_TEXT_FILE = os.environ.get("REFERENCE_TEXT", str(_sample_dir / "text.txt"))


def _load_dia_config() -> dict:
    db = SessionLocal()
    try:
        return ConfigManager(db).get_config("dia") or {}
    finally:
        db.close()


def _dia_base_url(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else _load_dia_config()
    return (cfg.get("url") or settings.dia_url).rstrip("/")


def _dia_timeout(cfg: dict | None = None, default: float = 300.0) -> float:
    cfg = cfg if cfg is not None else _load_dia_config()
    try:
        return float(cfg.get("timeout", default))
    except (TypeError, ValueError):
        return default

# Generation parameters
MAX_NEW_TOKENS = 3072
CFG_SCALE = 3.0
TEMPERATURE = 1.3
TOP_P = 0.95
CFG_FILTER_TOP_K = 30
SPEED_FACTOR = 0.94
SEED = -1
_SPEAKER_HEADER_RE = re.compile(r"^\s*\[(s\d+)\]\s*", re.IGNORECASE)


def _load_reference_text() -> str:
    if not os.path.exists(REFERENCE_TEXT_FILE):
        return ""
    with open(REFERENCE_TEXT_FILE, "r") as f:
        return f.read().strip()


def _ensure_s1_header(text: str | None) -> str:
    """Ensure Dia reference text starts with a single [S1] header."""
    normalized = (text or "").strip()
    if not normalized:
        return "[S1]"

    match = _SPEAKER_HEADER_RE.match(normalized)
    if not match:
        return f"[S1] {normalized}"

    if match.group(1).lower() == "s1":
        return normalized

    remainder = normalized[match.end() :].lstrip()
    return f"[S1] {remainder}" if remainder else "[S1]"


def get_wav_duration(filepath: str) -> float:
    """Get duration of a WAV file in seconds."""
    with wave.open(filepath, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)


async def generate(
    text: str,
    output_path: str,
    reference_audio_path: str | None = None,
    reference_text_override: str | None = None,
) -> str:
    """Generate audio from text using Dia voice cloning.

    Args:
        text: Sanitized text to generate (should NOT include [S1] tags).
        output_path: Full path to save the WAV file.
        reference_audio_path: Path to reference WAV for voice cloning.
            Defaults to REFERENCE_AUDIO.
        reference_text_override: Reference transcript text.
            Defaults to loading from REFERENCE_TEXT_FILE.

    Returns:
        Path to the generated WAV file.

    Raises:
        RuntimeError: If generation fails at any step.
    """
    cfg = _load_dia_config()
    base_url = _dia_base_url(cfg)
    ref_audio = reference_audio_path or REFERENCE_AUDIO
    reference_text = (
        reference_text_override
        if reference_text_override is not None
        else _load_reference_text()
    )
    reference_text = _ensure_s1_header(reference_text)

    # Dia expects: reference text with [S1], then new text, then [S2] to signal end
    text_to_generate = f"[S1] {text}\n[S2]"

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    timeout = httpx.Timeout(timeout=_dia_timeout(cfg))

    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1. Upload reference audio
        logger.info(f"Uploading reference audio: {ref_audio}")
        ref_filename = os.path.basename(ref_audio)
        with open(ref_audio, "rb") as audio_file:
            files = {"files": (ref_filename, audio_file, "audio/wav")}
            resp = await client.post(f"{base_url}/gradio_api/upload", files=files)

        if resp.status_code != 200:
            raise RuntimeError(f"Upload failed: {resp.status_code} {resp.text}")

        upload_data = resp.json()
        if not isinstance(upload_data, list) or len(upload_data) == 0:
            raise RuntimeError(f"Invalid upload response: {upload_data}")

        uploaded_file_path = upload_data[0]
        logger.info(f"Uploaded reference audio: {uploaded_file_path}")

        # 2. Initiate generation
        logger.info(f"Generating: {text[:80]}...")
        resp = await client.post(
            f"{base_url}/gradio_api/call/generate_audio",
            json={
                "data": [
                    text_to_generate,
                    reference_text,
                    {
                        "path": uploaded_file_path,
                        "meta": {"_type": "gradio.FileData"},
                    },
                    MAX_NEW_TOKENS,
                    CFG_SCALE,
                    TEMPERATURE,
                    TOP_P,
                    CFG_FILTER_TOP_K,
                    SPEED_FACTOR,
                    SEED,
                ]
            },
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Generation request failed: {resp.status_code} {resp.text}"
            )

        response_data = resp.json()
        if "event_id" not in response_data:
            raise RuntimeError(f"No event_id in response: {response_data}")

        event_id = response_data["event_id"]
        logger.info(f"Event ID: {event_id}")

        # 3. Poll SSE for result
        audio_url = None
        async with client.stream(
            "GET", f"{base_url}/gradio_api/call/generate_audio/{event_id}"
        ) as stream:
            async for line in stream.aiter_lines():
                if not line:
                    continue
                logger.debug(f"SSE: {line[:100]}")
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if isinstance(data, list) and len(data) > 0:
                            audio_data = data[0]
                            if isinstance(audio_data, dict) and "url" in audio_data:
                                audio_url = audio_data["url"]
                                logger.info(f"Audio URL: {audio_url}")
                                break
                    except json.JSONDecodeError:
                        continue

        if not audio_url:
            raise RuntimeError("No audio URL found in SSE response")

        # 4. Download the audio
        logger.info("Downloading audio...")
        resp = await client.get(audio_url)
        if resp.status_code != 200:
            raise RuntimeError(f"Audio download failed: {resp.status_code}")

        with open(output_path, "wb") as f:
            f.write(resp.content)

        file_size = os.path.getsize(output_path)
        logger.info(f"Saved: {output_path} ({file_size} bytes)")

        return output_path
