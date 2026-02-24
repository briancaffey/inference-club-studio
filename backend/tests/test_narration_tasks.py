import wave
from datetime import datetime, timezone
from pathlib import Path

from app.models.narration import (
    NarrationSegment,
    NarrationTranscription,
    NarrationVariant,
)
from app.models.project import Project
from app.services.narration.studio_voice import StudioVoiceEnhancementResult
from app.tasks import narration as narration_tasks


def _write_test_wav(path: Path, duration_ms: int = 400) -> None:
    sample_rate = 16000
    frames = int(sample_rate * duration_ms / 1000)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)


def _make_segment(db) -> NarrationSegment:
    project = Project(name="Narration Task Test", project_type="narration")
    db.add(project)
    db.commit()
    db.refresh(project)

    segment = NarrationSegment(
        project_id=project.id,
        position=1,
        text="This segment should keep audio even if STT fails.",
        sanitized_text="This segment should keep audio even if STT fails.",
        service="dia",
        status="pending",
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


def test_failed_generation_attempt_keeps_audio_for_review(db, monkeypatch, tmp_path):
    segment = _make_segment(db)
    output_dir = tmp_path / "narration"
    output_dir.mkdir(parents=True, exist_ok=True)

    async def fake_dia_generate(_text: str, output_path: str, **_kwargs) -> None:
        _write_test_wav(Path(output_path))

    async def failing_transcribe(_path: str):
        raise RuntimeError("STT unavailable")

    async def fake_enhance_audio(
        _source_audio_path: str,
        *,
        output_audio_path: str | None = None,
        check_health: bool = True,
        client=None,
    ) -> StudioVoiceEnhancementResult:
        assert check_health is True
        assert output_audio_path is not None
        _write_test_wav(Path(output_audio_path), duration_ms=400)
        return StudioVoiceEnhancementResult(
            status="cleaned",
            output_path=output_audio_path,
            error_message=None,
            cleaned_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(
        narration_tasks,
        "_project_output_dir",
        lambda _project_id: output_dir,
    )
    monkeypatch.setattr(narration_tasks, "dia_generate", fake_dia_generate)
    monkeypatch.setattr(
        narration_tasks,
        "transcribe_audio_file",
        failing_transcribe,
    )
    monkeypatch.setattr(
        narration_tasks,
        "enhance_audio_file",
        fake_enhance_audio,
    )

    result = narration_tasks._run_single_attempt(
        db=db,
        segment=segment,
        raw_text=segment.text,
        sanitized_text=segment.sanitized_text,
        attempt=1,
    )

    variant = (
        db.query(NarrationVariant)
        .filter(NarrationVariant.id == result.variant_id)
        .first()
    )
    assert variant is not None
    assert Path(result.output_path).exists()
    assert result.output_path == variant.audio_path
    assert result.studio_voice_status == "cleaned"
    assert result.studio_voice_audio_path is not None
    assert Path(result.studio_voice_audio_path).exists()
    assert result.quality.should_regenerate is True
    assert "No transcription returned from STT" in result.quality.reason

    narration_tasks._finalize_needs_review(db, segment, result, ["STT unavailable"])
    db.refresh(segment)

    assert segment.status == "error"
    assert segment.needs_review is True
    assert segment.audio_path == result.output_path
    assert segment.studio_voice_audio_path == result.studio_voice_audio_path
    assert segment.studio_voice_status == "cleaned"
    assert segment.selected_variant_id == result.variant_id
    assert segment.duration_seconds == result.duration_seconds

    transcription_count = (
        db.query(NarrationTranscription)
        .filter(NarrationTranscription.segment_id == segment.id)
        .count()
    )
    assert transcription_count == 0
