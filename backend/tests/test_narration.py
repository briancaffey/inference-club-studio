import wave
import io
import zipfile
from types import SimpleNamespace

from app.models.narration import (
    NarrationSegment,
    NarrationTranscription,
    NarrationVariant,
)
from app.models.narration_image import (
    NarrationImageFrame,
    NarrationImageFrameStatus,
    NarrationImageGenerationMode,
    NarrationImageSeries,
    NarrationImageSeriesStatus,
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
    assert segment["studio_voice_status"] == "not_cleaned"
    assert segment["studio_voice_audio_path"] is None
    assert segment["is_final"] is False
    assert segment["needs_review"] is False
    assert segment["last_generated_at"] is None

    list_resp = client.get(f"/api/projects/{project.id}/segments")
    assert list_resp.status_code == 200
    segments = list_resp.json()
    assert len(segments) == 1
    assert segments[0]["id"] == segment["id"]


def test_segment_flags_endpoint_updates_final_and_review_state(client, db):
    project = _make_narration_project(db)
    segment = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Needs review controls", "service": "dia"},
    ).json()

    mark_review = client.patch(
        f"/api/segments/{segment['id']}/flags",
        json={"needs_review": True},
    )
    assert mark_review.status_code == 200
    review_payload = mark_review.json()
    assert review_payload["needs_review"] is True
    assert review_payload["is_final"] is False

    mark_final = client.patch(
        f"/api/segments/{segment['id']}/flags",
        json={"is_final": True},
    )
    assert mark_final.status_code == 200
    final_payload = mark_final.json()
    assert final_payload["is_final"] is True
    assert final_payload["needs_review"] is False

    invalid = client.patch(f"/api/segments/{segment['id']}/flags", json={})
    assert invalid.status_code == 400


def test_mark_done_updates_error_segment_with_audio(client, db, tmp_path):
    project = _make_narration_project(db)
    segment_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Recover this segment", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == segment_payload["id"])
        .first()
    )
    assert segment is not None

    audio_path = tmp_path / "recover_segment.wav"
    _write_test_wav(str(audio_path), duration_ms=530)

    segment.status = "error"
    segment.audio_path = str(audio_path)
    segment.duration_seconds = None
    segment.error_message = "Generation flagged as error"
    segment.needs_review = True
    db.commit()

    response = client.post(f"/api/segments/{segment.id}/mark-done")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["error_message"] is None
    assert payload["needs_review"] is False
    assert payload["duration_seconds"] == 0.53

    db.refresh(segment)
    assert segment.status == "done"
    assert segment.error_message is None
    assert segment.needs_review is False
    assert segment.duration_seconds == 0.53


def test_mark_done_rejects_segment_without_audio(client, db):
    project = _make_narration_project(db)
    segment_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Cannot recover without audio", "service": "dia"},
    ).json()

    response = client.post(f"/api/segments/{segment_payload['id']}/mark-done")
    assert response.status_code == 400
    assert response.json()["detail"] == "Segment has no audio to mark done"


def test_regenerate_sets_needs_review_and_clears_final(client, db, monkeypatch):
    project = _make_narration_project(db)
    segment_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Please regenerate me", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == segment_payload["id"])
        .first()
    )
    assert segment is not None
    segment.is_final = True
    segment.needs_review = False
    db.commit()

    def fake_enqueue_generation_job(**kwargs):
        assert kwargs["segment_ids"] == [segment.id]
        assert kwargs["review_segment_ids"] == [segment.id]
        return narration.GenerationJob(
            id="regenerate-job",
            segment_ids=[segment.id],
            review_segment_ids=[segment.id],
            project_id=project.id,
        )

    async def fake_broadcast_job_queued(_job):
        return None

    monkeypatch.setattr(
        narration, "_enqueue_generation_job", fake_enqueue_generation_job
    )
    monkeypatch.setattr(narration, "_broadcast_job_queued", fake_broadcast_job_queued)

    response = client.post(f"/api/segments/{segment.id}/regenerate")
    assert response.status_code == 202

    db.refresh(segment)
    assert segment.needs_review is True
    assert segment.is_final is False


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


def _write_test_png(path: str) -> None:
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")


def test_export_timeline_metadata_and_images_zip(client, db, tmp_path):
    project = _make_narration_project(db)

    seg_1_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Segment one with images", "service": "dia"},
    ).json()
    seg_2_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Segment two without images", "service": "dia"},
    ).json()

    seg_1 = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == seg_1_payload["id"])
        .first()
    )
    seg_2 = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == seg_2_payload["id"])
        .first()
    )
    assert seg_1 is not None
    assert seg_2 is not None

    audio_1 = tmp_path / "seg1.wav"
    audio_2 = tmp_path / "seg2.wav"
    _write_test_wav(str(audio_1), duration_ms=3000)
    _write_test_wav(str(audio_2), duration_ms=2000)

    seg_1.status = "done"
    seg_1.audio_path = str(audio_1)
    seg_2.status = "done"
    seg_2.audio_path = str(audio_2)

    series = NarrationImageSeries(
        segment_id=seg_1.id,
        status=NarrationImageSeriesStatus.COMPLETED.value,
    )
    db.add(series)
    db.flush()

    for index in range(3):
        image_path = tmp_path / f"seg1_img_{index + 1}.png"
        _write_test_png(str(image_path))
        db.add(
            NarrationImageFrame(
                series_id=series.id,
                step_order=index + 1,
                prompt=f"Frame {index + 1}",
                mode=NarrationImageGenerationMode.TEXT_TO_IMAGE.value,
                status=NarrationImageFrameStatus.COMPLETED.value,
                output_image_path=str(image_path),
            )
        )

    db.commit()

    metadata_resp = client.get(
        f"/api/projects/{project.id}/export-timeline-metadata?fps=24"
    )
    assert metadata_resp.status_code == 200
    metadata = metadata_resp.json()
    assert metadata["audio_channel"] == 3
    assert metadata["image_channel"] == 4
    assert metadata["audio_volume"] == 1.9
    assert metadata["fps"] == 24

    segments = metadata["segments"]
    assert len(segments) == 2

    first = segments[0]
    assert first["segment_id"] == seg_1.id
    assert first["audio"]["start_frame"] == 1
    assert first["audio"]["end_frame_exclusive"] == 73
    assert first["audio"]["frame_count"] == 72
    assert [item["start_frame"] for item in first["images"]] == [1, 25, 49]
    assert [item["end_frame_exclusive"] for item in first["images"]] == [25, 49, 73]

    second = segments[1]
    assert second["segment_id"] == seg_2.id
    assert second["audio"]["start_frame"] == 73
    assert second["audio"]["end_frame_exclusive"] == 121
    assert second["images"] == []

    images_zip_resp = client.get(f"/api/projects/{project.id}/export-images-zip")
    assert images_zip_resp.status_code == 200

    with zipfile.ZipFile(io.BytesIO(images_zip_resp.content), "r") as archive:
        names = sorted(archive.namelist())
    assert names == sorted(item["filename"] for item in first["images"])


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

    monkeypatch.setattr(narration.settings, "studio_voice_auto_clean", False)
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


def test_trim_segment_auto_cleans_when_enabled(client, db, monkeypatch, tmp_path):
    project = _make_narration_project(db)
    created = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Trim and clean this", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == created["id"]).first()
    )
    assert segment is not None

    audio_path = tmp_path / "trim_clean_target.wav"
    _write_test_wav(str(audio_path), duration_ms=1000)

    segment.status = "done"
    segment.audio_path = str(audio_path)
    segment.duration_seconds = 1.0

    variant = NarrationVariant(
        segment_id=segment.id,
        text=segment.text,
        sanitized_text=segment.sanitized_text,
        service=segment.service,
        audio_path=str(audio_path),
        duration_seconds=1.0,
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)

    segment.selected_variant_id = variant.id
    db.commit()

    cleaned_path = tmp_path / "trim_clean_target_studio_voice.wav"
    enhance_calls = {}

    async def fake_transcribe(_audio_path: str):
        return "trim cleaned", [{"word": "trim", "start": 0.0, "end": 0.1}]

    async def fake_enhance(
        source_audio_path: str,
        *,
        output_audio_path: str | None = None,
        check_health: bool = True,
        client=None,
    ):
        _write_test_wav(str(cleaned_path), duration_ms=700)
        enhance_calls["source_audio_path"] = source_audio_path
        enhance_calls["output_audio_path"] = output_audio_path
        enhance_calls["check_health"] = check_health
        return SimpleNamespace(
            status="cleaned",
            output_path=str(cleaned_path),
            error_message=None,
            cleaned_at=None,
        )

    monkeypatch.setattr(narration.settings, "studio_voice_auto_clean", True)
    monkeypatch.setattr(narration, "_transcribe_audio_file", fake_transcribe)
    monkeypatch.setattr(narration, "enhance_audio_file", fake_enhance)

    response = client.post(
        f"/api/segments/{segment.id}/trim",
        json={"start_ms": 100, "end_ms": 400, "mode": "remove"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["segment"]["studio_voice_status"] == "cleaned"
    assert payload["segment"]["studio_voice_audio_path"] == str(cleaned_path)
    assert enhance_calls["source_audio_path"] == str(audio_path)
    assert enhance_calls["output_audio_path"] == narration.studio_voice_output_path(
        str(audio_path)
    )
    assert enhance_calls["check_health"] is True

    db.refresh(segment)
    db.refresh(variant)
    assert segment.studio_voice_status == "cleaned"
    assert segment.studio_voice_audio_path == str(cleaned_path)
    assert variant.studio_voice_status == "cleaned"
    assert variant.studio_voice_audio_path == str(cleaned_path)


def test_trim_segment_allows_error_status_when_audio_exists(
    client, db, monkeypatch, tmp_path
):
    project = _make_narration_project(db)
    created = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Trim even if errored", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment).filter(NarrationSegment.id == created["id"]).first()
    )
    assert segment is not None

    audio_path = tmp_path / "trim_error_target.wav"
    _write_test_wav(str(audio_path), duration_ms=1000)

    segment.status = "error"
    segment.audio_path = str(audio_path)
    segment.duration_seconds = 1.0
    db.commit()

    async def fake_transcribe(_audio_path: str):
        return "trimmed error segment", [{"word": "trimmed", "start": 0.0, "end": 0.2}]

    monkeypatch.setattr(narration.settings, "studio_voice_auto_clean", False)
    monkeypatch.setattr(narration, "_transcribe_audio_file", fake_transcribe)

    response = client.post(
        f"/api/segments/{segment.id}/trim",
        json={"start_ms": 200, "end_ms": 500, "mode": "remove"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["segment"]["status"] == "error"
    assert payload["segment"]["duration_seconds"] == 0.7
    assert payload["transcription"]["text"] == "trimmed error segment"
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
        assert segment["studio_voice_status"] == "not_cleaned"


def test_studio_voice_clean_all_queues_only_uncleaned_items(
    client,
    db,
    monkeypatch,
    tmp_path,
):
    project = _make_narration_project(db)
    segment_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Hello cleaned world", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == segment_payload["id"])
        .first()
    )
    assert segment is not None

    audio_path = tmp_path / "segment.wav"
    _write_test_wav(str(audio_path), duration_ms=600)
    segment.status = "done"
    segment.audio_path = str(audio_path)
    segment.studio_voice_audio_path = None
    db.commit()

    class DummyTask:
        id = "studio-voice-task"

    def fake_apply_async(*args, **kwargs):
        return DummyTask()

    monkeypatch.setattr(
        narration.clean_project_studio_voice_task,
        "apply_async",
        fake_apply_async,
    )

    response = client.post(f"/api/projects/{project.id}/studio-voice/clean-all")
    assert response.status_code == 202
    payload = response.json()
    assert payload["queued"] == 1
    assert payload["task_id"] == "studio-voice-task"


def test_studio_voice_clean_all_skips_when_already_cleaned(client, db, tmp_path):
    project = _make_narration_project(db)
    segment_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Already cleaned", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == segment_payload["id"])
        .first()
    )
    assert segment is not None

    audio_path = tmp_path / "segment.wav"
    cleaned_path = tmp_path / "segment_studio_voice.wav"
    _write_test_wav(str(audio_path), duration_ms=450)
    _write_test_wav(str(cleaned_path), duration_ms=450)

    segment.status = "done"
    segment.audio_path = str(audio_path)
    segment.studio_voice_audio_path = str(cleaned_path)
    segment.studio_voice_status = "cleaned"
    db.commit()

    response = client.post(f"/api/projects/{project.id}/studio-voice/clean-all")
    assert response.status_code == 202
    payload = response.json()
    assert payload["queued"] == 0
    assert "already Studio Voice cleaned" in payload["message"]


def test_audio_endpoint_relinks_missing_segment_path_from_variant(client, db, tmp_path):
    project = _make_narration_project(db)
    segment_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Relink my audio", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == segment_payload["id"])
        .first()
    )
    assert segment is not None

    variant_audio_path = tmp_path / "variant.wav"
    _write_test_wav(str(variant_audio_path), duration_ms=420)

    segment.status = "done"
    segment.audio_path = str(tmp_path / "missing.wav")
    variant = NarrationVariant(
        segment_id=segment.id,
        text=segment.text,
        sanitized_text=segment.sanitized_text,
        service=segment.service,
        audio_path=str(variant_audio_path),
        duration_seconds=0.42,
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)

    segment.selected_variant_id = variant.id
    db.commit()

    response = client.get(f"/api/segments/{segment.id}/audio")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")

    db.refresh(segment)
    assert segment.audio_path == str(variant_audio_path)
    assert segment.selected_variant_id == variant.id


def test_waveform_endpoint_returns_normalized_samples(client, db, tmp_path):
    project = _make_narration_project(db)
    segment_payload = client.post(
        f"/api/projects/{project.id}/segments",
        json={"text": "Waveform me", "service": "dia"},
    ).json()

    segment = (
        db.query(NarrationSegment)
        .filter(NarrationSegment.id == segment_payload["id"])
        .first()
    )
    assert segment is not None

    audio_path = tmp_path / "waveform.wav"
    _write_test_wav(str(audio_path), duration_ms=700)

    segment.status = "done"
    segment.audio_path = str(audio_path)
    db.commit()

    response = client.get(f"/api/segments/{segment.id}/waveform?points=128")
    assert response.status_code == 200
    payload = response.json()
    assert payload["segment_id"] == segment.id
    assert payload["source"] == "original"
    assert payload["points"] == 128
    assert len(payload["samples"]) == 128
    assert payload["duration_ms"] >= 690
    assert payload["duration_ms"] <= 710
    assert max(payload["samples"]) <= 1.0
    assert min(payload["samples"]) >= 0.0


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
