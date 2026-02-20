"""Speech-to-text helper for narration audio files."""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def transcribe_audio_file(audio_path: str) -> tuple[str, list[dict]]:
    with open(audio_path, "rb") as source:
        audio_bytes = source.read()

    timeout = httpx.Timeout(connect=10, read=120, write=10, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.stt_url.rstrip('/')}/transcribe",
            params={"timestamps": "true"},
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"STT service returned {response.status_code}: {response.text[:300]}"
        )

    payload = response.json()
    return payload.get("text", ""), payload.get("words", [])
