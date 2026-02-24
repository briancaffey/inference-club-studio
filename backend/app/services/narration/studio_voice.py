"""Studio Voice post-processing helpers for narration audio."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydub import AudioSegment

from app.clients.studio_voice.client import StudioVoiceClient
from app.config import settings

logger = logging.getLogger(__name__)

STUDIO_VOICE_STATUS_NOT_CLEANED = "not_cleaned"
STUDIO_VOICE_STATUS_CLEANED = "cleaned"
STUDIO_VOICE_STATUS_UNAVAILABLE = "unavailable"
STUDIO_VOICE_STATUS_ERROR = "error"

StudioVoiceStatus = Literal[
    "not_cleaned",
    "cleaned",
    "unavailable",
    "error",
]


@dataclass
class StudioVoiceEnhancementResult:
    status: StudioVoiceStatus
    output_path: str | None = None
    error_message: str | None = None
    cleaned_at: datetime | None = None


def studio_voice_output_path(source_audio_path: str) -> str:
    source = Path(source_audio_path)
    return str(source.with_name(f"{source.stem}_studio_voice.wav"))


def _prepare_wav_for_studio_voice(source_audio_path: str) -> str:
    segment = AudioSegment.from_file(source_audio_path)
    segment = segment.set_frame_rate(settings.studio_voice_input_sample_rate)
    segment = segment.set_channels(1)
    segment = segment.set_sample_width(2)

    handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = handle.name
    handle.close()
    segment.export(temp_path, format="wav")
    return temp_path


async def is_studio_voice_ready(client: StudioVoiceClient | None = None) -> bool:
    svc = client or StudioVoiceClient()
    try:
        return await svc.check_health()
    except Exception as exc:
        logger.debug("Studio Voice readiness check failed: %s", exc)
        return False


async def enhance_audio_file(
    source_audio_path: str,
    *,
    output_audio_path: str | None = None,
    check_health: bool = True,
    client: StudioVoiceClient | None = None,
) -> StudioVoiceEnhancementResult:
    source_path = Path(source_audio_path)
    if not source_path.exists():
        return StudioVoiceEnhancementResult(
            status=STUDIO_VOICE_STATUS_ERROR,
            error_message=f"Audio file not found: {source_audio_path}",
        )

    svc = client or StudioVoiceClient()
    if check_health:
        ready = await is_studio_voice_ready(client=svc)
        if not ready:
            return StudioVoiceEnhancementResult(
                status=STUDIO_VOICE_STATUS_UNAVAILABLE,
                error_message=(
                    "Studio Voice service is unavailable; skipping enhancement"
                ),
            )

    temp_input_path: str | None = None
    try:
        temp_input_path = _prepare_wav_for_studio_voice(str(source_path))
        prepared_bytes = Path(temp_input_path).read_bytes()

        enhanced_bytes = await svc.enhance_audio(
            prepared_bytes,
            filename=source_path.name,
        )

        destination_path = Path(
            output_audio_path or studio_voice_output_path(str(source_path))
        )
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(enhanced_bytes)

        return StudioVoiceEnhancementResult(
            status=STUDIO_VOICE_STATUS_CLEANED,
            output_path=str(destination_path),
            cleaned_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.warning("Studio Voice enhancement failed for %s: %s", source_path, exc)
        return StudioVoiceEnhancementResult(
            status=STUDIO_VOICE_STATUS_ERROR,
            error_message=str(exc)[:1000],
        )
    finally:
        if temp_input_path:
            try:
                Path(temp_input_path).unlink(missing_ok=True)
            except Exception:
                logger.debug(
                    "Failed to remove temporary Studio Voice input file: %s",
                    temp_input_path,
                )
