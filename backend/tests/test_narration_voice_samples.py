import wave
from pathlib import Path

from app.models.narration import NarrationVoiceSample
from app.routes import narration


def _write_test_wav(path: Path, duration_ms: int = 1000) -> None:
    sample_rate = 16000
    frames = int(sample_rate * duration_ms / 1000)

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)


def _setup_voice_dirs(monkeypatch, tmp_path: Path) -> None:
    samples_dir = tmp_path / "voice_samples"
    drafts_dir = samples_dir / "drafts"
    samples_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(narration, "VOICE_SAMPLES_DIR", samples_dir)
    monkeypatch.setattr(narration, "VOICE_SAMPLE_DRAFTS_DIR", drafts_dir)
    narration.voice_sample_drafts.clear()


def test_create_voice_sample_draft_extracts_and_transcribes(
    client, monkeypatch, tmp_path
):
    _setup_voice_dirs(monkeypatch, tmp_path)

    def fake_extract(_source: Path, destination: Path) -> None:
        _write_test_wav(destination, duration_ms=900)

    async def fake_transcribe(_path: str):
        return "hello world", [{"word": "hello", "start": 0.0, "end": 0.4}]

    monkeypatch.setattr(narration, "_extract_voice_clip_to_wav", fake_extract)
    monkeypatch.setattr(narration, "_transcribe_audio_file_or_502", fake_transcribe)

    resp = client.post(
        "/api/voice-samples/drafts",
        files={"clip": ("sample.mp4", b"video-bytes", "video/mp4")},
    )
    assert resp.status_code == 201

    payload = resp.json()
    assert payload["transcription"] == "hello world"
    assert payload["duration_seconds"] > 0
    assert payload["id"] in narration.voice_sample_drafts


def test_trim_voice_sample_draft_retranscribes(client, monkeypatch, tmp_path):
    _setup_voice_dirs(monkeypatch, tmp_path)

    draft_audio = narration.VOICE_SAMPLE_DRAFTS_DIR / "draft.wav"
    _write_test_wav(draft_audio, duration_ms=1200)

    narration.voice_sample_drafts["draft"] = narration.VoiceSampleDraft(
        id="draft",
        audio_path=str(draft_audio),
        source_path=None,
        original_filename="draft.wav",
        transcription="before",
        words=[],
    )

    async def fake_transcribe(_path: str):
        return "after trim", [{"word": "after", "start": 0.0, "end": 0.2}]

    monkeypatch.setattr(narration, "_transcribe_audio_file_or_502", fake_transcribe)

    resp = client.post(
        "/api/voice-samples/drafts/draft/trim",
        json={"start_ms": 200, "end_ms": 700},
    )
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["transcription"] == "after trim"
    assert payload["duration_seconds"] < 1.2


def test_finalize_voice_sample_draft_creates_saved_sample(
    client, monkeypatch, tmp_path
):
    _setup_voice_dirs(monkeypatch, tmp_path)

    draft_audio = narration.VOICE_SAMPLE_DRAFTS_DIR / "save_me.wav"
    _write_test_wav(draft_audio, duration_ms=800)

    narration.voice_sample_drafts["save-me"] = narration.VoiceSampleDraft(
        id="save-me",
        audio_path=str(draft_audio),
        source_path=None,
        original_filename="save_me.wav",
        transcription="draft transcript",
        words=[],
    )

    resp = client.post(
        "/api/voice-samples/drafts/save-me/finalize",
        json={"name": "Test Voice", "transcript": "custom transcript"},
    )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["name"] == "Test Voice"
    assert payload["transcript"] == "custom transcript"
    assert payload["id"] > 0
    assert "save-me" not in narration.voice_sample_drafts


def test_update_voice_sample_transcript(client, db, tmp_path):
    sample_audio = tmp_path / "sample.wav"
    _write_test_wav(sample_audio, duration_ms=500)

    sample = NarrationVoiceSample(
        name="Editable Voice",
        audio_path=str(sample_audio),
        transcript="before text",
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)

    resp = client.patch(
        f"/api/voice-samples/{sample.id}",
        json={"transcript": "after text"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == sample.id
    assert payload["transcript"] == "after text"

    db.refresh(sample)
    assert sample.transcript == "after text"
