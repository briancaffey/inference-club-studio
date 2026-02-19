"""Magpie TTS client via NVIDIA NIM REST API."""

import logging
import os
import wave

import httpx

logger = logging.getLogger(__name__)

MAGPIE_URL = os.environ.get("MAGPIE_URL", "http://192.168.6.3:9000")
DEFAULT_VOICE = os.environ.get("MAGPIE_VOICE", "Magpie-Multilingual.EN-US.Mia.Happy")
DEFAULT_LANGUAGE = "en-US"
DEFAULT_SAMPLE_RATE = 22050


def get_wav_duration(filepath: str) -> float:
    """Get duration of a WAV file in seconds."""
    with wave.open(filepath, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)


async def list_voices() -> list[str]:
    """List available Magpie voices."""
    base_url = MAGPIE_URL.rstrip("/")
    timeout = httpx.Timeout(timeout=30.0)

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
    base_url = MAGPIE_URL.rstrip("/")
    voice = voice or DEFAULT_VOICE

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    logger.info(f"Magpie generating: {text[:80]}... (voice={voice})")

    timeout = httpx.Timeout(timeout=60.0)

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
            raise RuntimeError(f"Magpie synthesis failed: {resp.status_code} {resp.text}")

        with open(output_path, "wb") as f:
            f.write(resp.content)

        file_size = os.path.getsize(output_path)
        logger.info(f"Saved: {output_path} ({file_size} bytes)")

        return output_path
