"""Audio post-processing utilities for narration export."""

import io

from pydub import AudioSegment


TARGET_SAMPLE_RATE = 44100
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # 16-bit


def load_and_normalize(path: str) -> AudioSegment:
    """Load a WAV file and convert to 44100Hz mono 16-bit."""
    seg = AudioSegment.from_file(path)
    if seg.frame_rate != TARGET_SAMPLE_RATE:
        seg = seg.set_frame_rate(TARGET_SAMPLE_RATE)
    if seg.channels != TARGET_CHANNELS:
        seg = seg.set_channels(TARGET_CHANNELS)
    if seg.sample_width != TARGET_SAMPLE_WIDTH:
        seg = seg.set_sample_width(TARGET_SAMPLE_WIDTH)
    return seg


def apply_fade(seg: AudioSegment, fade_ms: int) -> AudioSegment:
    """Apply fade-in and fade-out to eliminate clicks at boundaries."""
    if fade_ms <= 0:
        return seg
    # Don't fade longer than half the segment
    fade_ms = min(fade_ms, len(seg) // 2)
    if fade_ms <= 0:
        return seg
    return seg.fade_in(fade_ms).fade_out(fade_ms)


def peak_normalize(seg: AudioSegment, headroom_db: float = 0.5) -> AudioSegment:
    """Normalize peak level to -headroom_db dBFS."""
    change = -headroom_db - seg.max_dBFS
    return seg.apply_gain(change)


def concatenate_segments(
    paths: list[str],
    gap_ms: int = 750,
    fade_ms: int = 50,
    normalize: bool = True,
) -> AudioSegment:
    """Load all audio files, process, and join with silence gaps."""
    silence = AudioSegment.silent(duration=gap_ms, frame_rate=TARGET_SAMPLE_RATE)
    combined = AudioSegment.empty()

    for i, path in enumerate(paths):
        seg = load_and_normalize(path)
        if fade_ms > 0:
            seg = apply_fade(seg, fade_ms)
        if normalize:
            seg = peak_normalize(seg)
        if i > 0:
            combined += silence
        combined += seg

    return combined


def trim_audio(path: str, start_ms: int, end_ms: int) -> float:
    """Trim audio file in place. Returns new duration in seconds."""
    seg = AudioSegment.from_file(path)
    trimmed = seg[start_ms:end_ms]
    trimmed.export(path, format="wav")
    return len(trimmed) / 1000.0


def export_audio(
    combined: AudioSegment,
    fmt: str = "wav",
    bitrate: str = "192k",
) -> tuple[io.BytesIO, str]:
    """Export combined audio to bytes. Returns (buffer, media_type)."""
    buf = io.BytesIO()
    if fmt == "mp3":
        combined.export(buf, format="mp3", bitrate=bitrate)
        media_type = "audio/mpeg"
    else:
        combined.export(buf, format="wav")
        media_type = "audio/wav"
    buf.seek(0)
    return buf, media_type
