import wave

from app.models.narration import (
    NarrationSegment,
    NarrationTranscription,
    NarrationVariant,
)
from app.models.project import Project
from app.routes import narration


def _make_project(db, name="Video Project"):
    project = Project(name=name, project_type="video_to_video")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_narration_project(db, name="Narration Project"):
    project = Project(name=name, project_type="narration")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_legacy_narration_projects_only_list_narration(client, db):
    video_project = _make_project(db, "Video")
    narration_project = _make_narration_project(db, "Narration")

    resp = client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert str(narration_project.id) in ids
    assert str(video_project.id) not in ids


def test_create_and_list_segments(client, db):
    project = _make_narration_project(db)

    create_resp = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Hello world", "service": "dia"},
    )
    assert create_resp.status_code == 201
    segment = create_resp.json()
    assert segment["text"] == "Hello world"
    assert segment["status"] == "pending"

    list_resp = client.get(f"/api/projects/{project.id}/segments")
    assert list_resp.status_code == 200
    segments = list_resp.json()
    assert len(segments) == 1
    assert segments[0]["id"] == segment["id"]


def test_narration_segments_reject_video_project(client, db):
    project = _make_project(db)
    resp = client.get(f"/api/projects/{project.id}/segments")
    assert resp.status_code == 400


def _write_test_wav(path: str, duration_ms: int = 300) -> None:
    sample_rate = 16000
    frames = int(sample_rate * duration_ms / 1000)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)


def _wav_duration_ms(path: str) -> int:
    with wave.open(path, "rb") as handle:
        sample_rate = handle.getframerate()
        frames = handle.getnframes()
    return round((frames / sample_rate) * 1000)


def test_trim_segment_remove_mode_cuts_selected_range(
    client, db, monkeypatch, tmp_path
):
    project = _make_narration_project(db)
    created = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Trim this deadspace", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == created["id"]).first()
    )
    assert segment is not None

    audio_path = tmp_path / "trim_target.wav"
    _write_test_wav(str(audio_path), duration_ms=1000)

    segment.status = "done"
    segment.audio_path = str(audio_path)
    segment.duration_seconds = 1.0
    db.add(
        NarrationTranscription(
            segment_id=segment.id,
            text="before trim",
            words_json=[{"word": "before", "start": 0.0, "end": 0.2}],
        )
    )
    db.commit()

    async def fake_transcribe(_audio_path: str):
        return "after trim", [{"word": "after", "start": 0.0, "end": 0.2}]

    monkeypatch.setattr(narration, "_transcribe_audio_file", fake_transcribe)

    resp = client.post(
        f"/api/segments/{segment.id}/trim",
        json={"start_ms": 200, "end_ms": 500, "mode": "remove"},
    )
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["segment"]["duration_seconds"] == 0.7
    assert payload["transcription"]["text"] == "after trim"
    assert abs(_wav_duration_ms(str(audio_path)) - 700) <= 2


def test_split_segment_replaces_segment_and_preserves_order(client, db, tmp_path):
    project = _make_narration_project(db)

    seg_a = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Segment A keeps its place.", "service": "dia"},
    ).json()
    seg_b = client.post(
        f"/api/projects/{project.id}/segments",
        json={
            "text": (
                "First sentence is short. "
                "Second sentence adds context. "
                "Third sentence adds more detail. "
                "Fourth sentence closes."
            ),
            "service": "dia",
        },
    ).json()
    seg_c = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Segment C should move later.", "service": "dia"},
    ).json()

    segment_b = (
        db.query(NarrationSegment).filter(NarrationSegment.id == seg_b["id"]).first()
    )
    assert segment_b is not None

    segment_audio = tmp_path / "segment_b.wav"
    variant_audio = tmp_path / "segment_b_variant.wav"
    _write_test_wav(str(segment_audio))
    _write_test_wav(str(variant_audio))

    segment_b.status = "done"
    segment_b.audio_path = str(segment_audio)
    segment_b.duration_seconds = 0.3

    variant = NarrationVariant(
        segment_id=segment_b.id,
        text=segment_b.text,
        sanitized_text=segment_b.sanitized_text,
        service=segment_b.service,
        audio_path=str(variant_audio),
        duration_seconds=0.3,
    )
    transcription = NarrationTranscription(
        segment_id=segment_b.id,
        text="temporary transcript",
        words_json=[{"word": "temporary", "start": 0.0, "end": 0.2}],
    )
    db.add(variant)
    db.add(transcription)
    db.commit()

    preview_resp = client.post(
        f"/api/segments/{segment_b.id}/split/preview",
        json={"target_words": 10},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["can_split"] is True
    assert len(preview["groups"]) >= 2

    split_resp = client.post(
        f"/api/segments/{segment_b.id}/split",
        json={"target_words": 10},
    )
    assert split_resp.status_code == 200
    payload = split_resp.json()
    updated = payload["segments"]

    assert [segment["position"] for segment in updated] == list(
        range(1, len(updated) + 1)
    )
    assert [segment["text"] for segment in updated] == [
        seg_a["text"],
        *[group["text"] for group in preview["groups"]],
        seg_c["text"],
    ]

    updated_ids = {segment["id"] for segment in updated}
    assert seg_b["id"] not in updated_ids
    assert seg_a["id"] in updated_ids
    assert seg_c["id"] in updated_ids

    assert segment_audio.exists() is False
    assert variant_audio.exists() is False

    removed_segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == seg_b["id"]).first()
    )
    assert removed_segment is None
    assert (
        db.query(NarrationVariant)
        .filter(NarrationVariant.segment_id == seg_b["id"])
        .count()
        == 0
    )
    assert (
        db.query(NarrationTranscription)
        .filter(NarrationTranscription.segment_id == seg_b["id"])
        .count()
        == 0
    )

    middle_segments = updated[1:-1]
    assert middle_segments
    for segment in middle_segments:
        assert segment["status"] == "pending"
        assert segment["service"] == "dia"


def test_split_segment_rejects_unsplittable_text(client, db):
    project = _make_narration_project(db)

    segment = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Short sentence only", "service": "dia"},
    ).json()

    resp = client.post(
        f"/api/segments/{segment['id']}/split",
        json={"target_words": 30},
    )
    assert resp.status_code == 400
    assert "multiple sentence groups" in resp.json()["detail"]
