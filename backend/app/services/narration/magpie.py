"""Magpie TTS client via NVIDIA NIM REST API."""

import logging
import os
import wave

import httpx

from app.config import settings
from app.database import SessionLocal
from app.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

DEFAULT_VOICE = os.environ.get("MAGPIE_VOICE", "Magpie-Multilingual.EN-US.Mia.Happy")
DEFAULT_LANGUAGE = "en-US"
DEFAULT_SAMPLE_RATE = 22050


def _load_magpie_config() -> dict:
    db = SessionLocal()
    try:
        return ConfigManager(db).get_config("magpie") or {}
    finally:
        db.close()


def _magpie_base_url(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else _load_magpie_config()
    return (cfg.get("url") or settings.magpie_url).rstrip("/")


def _magpie_timeout(cfg: dict | None = None, default: float = 60.0) -> float:
    cfg = cfg if cfg is not None else _load_magpie_config()
    try:
        return float(cfg.get("timeout", default))
    except (TypeError, ValueError):
        return default


def get_wav_duration(filepath: str) -> float:
    """Get duration of a WAV file in seconds."""
    with wave.open(filepath, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)


async def list_voices() -> list[str]:
    """List available Magpie voices."""
    cfg = _load_magpie_config()
    base_url = _magpie_base_url(cfg)
    timeout = httpx.Timeout(timeout=_magpie_timeout(cfg, default=30.0))

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{base_url}/v1/audio/list_voices")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to list voices: {resp.status_code} {resp.text}")

        data = resp.json()
        voices = []
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict) and "voices" in value:
                    voices.extend(value["voices"])
        return voices


async def generate(text: str, output_path: str, voice: str | None = None) -> str:
    """Generate audio from text using Magpie TTS.

    Args:
        text: Sanitized text to synthesize.
        output_path: Full path to save the WAV file.
        voice: Magpie voice name. Defaults to DEFAULT_VOICE.

    Returns:
        Path to the generated WAV file.

    Raises:
        RuntimeError: If generation fails.
    """
    cfg = _load_magpie_config()
    base_url = _magpie_base_url(cfg)
    voice = voice or DEFAULT_VOICE

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    logger.info(f"Magpie generating: {text[:80]}... (voice={voice})")

    timeout = httpx.Timeout(timeout=_magpie_timeout(cfg, default=60.0))

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/v1/audio/synthesize",
            data={
                "text": text,
                "language": DEFAULT_LANGUAGE,
                "voice": voice,
                "sample_rate_hz": DEFAULT_SAMPLE_RATE,
            },
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Magpie synthesis failed: {resp.status_code} {resp.text}"
            )

        with open(output_path, "wb") as f:
            f.write(resp.content)

        file_size = os.path.getsize(output_path)
        logger.info(f"Saved: {output_path} ({file_size} bytes)")

        return output_path
