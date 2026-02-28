from unittest.mock import patch

from app.models.narration import NarrationSegment
from app.models.narration_image import (
    NarrationImageFrame,
    NarrationImageFrameStatus,
    NarrationImageGenerationMode,
    NarrationImageSeries,
    NarrationImageSeriesStatus,
)
from app.models.project import Project
from app.services.narration_images import SequencePlan, SequencePlanStep


def _make_narration_project(db, name="Narration Project"):
    project = Project(name=name, project_type="narration")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_segment(db, project, position=1, text="Narration segment"):
    segment = NarrationSegment(
        project_id=project.id,
        position=position,
        text=text,
        sanitized_text=text,
        service="dia",
        status="done",
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


@patch("app.routes.narration_images.generate_narration_image_series")
@patch("app.routes.narration_images.generate_image_sequence_plan")
def test_auto_create_image_series_from_plan(mock_plan, mock_task, client, db):
    project = _make_narration_project(db)
    segment = _make_segment(db, project, text="A boy in a classroom.")

    mock_plan.return_value = SequencePlan(
        series_name="Classroom branch",
        steps=[
            SequencePlanStep(
                id="step_1",
                parent_id=None,
                mode="text_to_image",
                is_fork=False,
                prompt="A boy is sitting in a classroom, realistic style.",
            ),
            SequencePlanStep(
                id="step_2",
                parent_id="step_1",
                mode="image_to_image",
                is_fork=True,
                prompt="The boy is using a laptop, same composition.",
            ),
        ],
    )

    response = client.post(
        f"/api/segments/{segment.id}/image-series/auto",
        json={
            "creative_direction": "Keep continuity and add laptop usage.",
            "target_images": 2,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == NarrationImageSeriesStatus.QUEUED.value
    assert payload["name"] == "Classroom branch"
    assert len(payload["frames"]) == 2
    assert (
        payload["frames"][0]["mode"] == NarrationImageGenerationMode.TEXT_TO_IMAGE.value
    )
    assert (
        payload["frames"][1]["mode"]
        == NarrationImageGenerationMode.IMAGE_TO_IMAGE.value
    )
    assert mock_task.delay.call_count == 1


def test_sequence_plan_allows_multiple_roots():
    plan = SequencePlan(
        series_name="Independent scenes",
        steps=[
            SequencePlanStep(
                id="step_1",
                parent_id=None,
                mode="text_to_image",
                is_fork=False,
                prompt="Stock market line chart on trading monitors.",
            ),
            SequencePlanStep(
                id="step_2",
                parent_id=None,
                mode="text_to_image",
                is_fork=False,
                prompt="Kids in a classroom, natural daylight.",
            ),
            SequencePlanStep(
                id="step_3",
                parent_id="step_2",
                mode="image_to_image",
                is_fork=False,
                prompt="Same classroom scene, one kid using a laptop.",
            ),
            SequencePlanStep(
                id="step_4",
                parent_id=None,
                mode="text_to_image",
                is_fork=False,
                prompt="Couple planning a trip with maps on a table.",
            ),
        ],
    )

    assert len(plan.steps) == 4
    assert sum(1 for step in plan.steps if step.parent_id is None) == 3


@patch("app.routes.narration_images.generate_narration_image_series")
@patch("app.routes.narration_images.generate_image_sequence_plan")
def test_auto_create_image_series_supports_independent_steps(
    mock_plan, mock_task, client, db
):
    project = _make_narration_project(db)
    segment = _make_segment(
        db,
        project,
        text=(
            "The stock market was doing great, your kids were in school, "
            "you were going to restaurants and shaking hands and planning trips."
        ),
    )

    mock_plan.return_value = SequencePlan(
        series_name="Market to travel",
        steps=[
            SequencePlanStep(
                id="step_1",
                parent_id=None,
                mode="text_to_image",
                is_fork=False,
                prompt="Stock market dashboard with rising chart.",
            ),
            SequencePlanStep(
                id="step_2",
                parent_id=None,
                mode="text_to_image",
                is_fork=False,
                prompt="Kids in a classroom with teacher.",
            ),
            SequencePlanStep(
                id="step_3",
                parent_id=None,
                mode="text_to_image",
                is_fork=False,
                prompt="People in a restaurant shaking hands.",
            ),
            SequencePlanStep(
                id="step_4",
                parent_id="step_3",
                mode="image_to_image",
                is_fork=False,
                prompt="Same handshake scene, stronger focus on handshake.",
            ),
            SequencePlanStep(
                id="step_5",
                parent_id=None,
                mode="text_to_image",
                is_fork=False,
                prompt="Couple planning a trip at a table with tickets.",
            ),
        ],
    )

    response = client.post(
        f"/api/segments/{segment.id}/image-series/auto",
        json={
            "creative_direction": "Use mostly unrelated scenes with one continuity beat.",
            "target_images": 5,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    frames = payload["frames"]
    assert len(frames) == 5

    assert frames[0]["parent_frame_id"] is None
    assert frames[1]["parent_frame_id"] is None
    assert frames[2]["parent_frame_id"] is None
    assert frames[3]["parent_frame_id"] == frames[2]["id"]
    assert frames[4]["parent_frame_id"] is None
    assert mock_task.delay.call_count == 1


def test_add_frame_with_parent_defaults_to_image_to_image(client, db):
    project = _make_narration_project(db)
    segment = _make_segment(db, project)
    series = NarrationImageSeries(segment_id=segment.id, status="draft")
    db.add(series)
    db.flush()
    root = NarrationImageFrame(
        series_id=series.id,
        prompt="A man sitting on a bench",
        mode=NarrationImageGenerationMode.TEXT_TO_IMAGE.value,
        status=NarrationImageFrameStatus.COMPLETED.value,
        step_order=1,
    )
    db.add(root)
    db.commit()
    db.refresh(series)
    db.refresh(root)

    response = client.post(
        f"/api/image-series/{series.id}/frames",
        json={
            "prompt": "The man is wearing a cowboy hat",
            "parent_frame_id": str(root.id),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == NarrationImageGenerationMode.IMAGE_TO_IMAGE.value
    assert payload["is_fork"] is True
    assert payload["step_order"] == 2


def test_create_series_frame_defaults_to_1360x768(client, db):
    project = _make_narration_project(db)
    segment = _make_segment(db, project, text="A wide cinematic view.")

    response = client.post(
        f"/api/segments/{segment.id}/image-series",
        json={
            "name": "Cinematic default",
            "initial_prompt": "A cinematic wide shot of a city at dawn.",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert len(payload["frames"]) == 1
    assert payload["frames"][0]["width"] == 1360
    assert payload["frames"][0]["height"] == 768


def test_add_frame_defaults_to_1360x768(client, db):
    project = _make_narration_project(db)
    segment = _make_segment(db, project)
    series = NarrationImageSeries(segment_id=segment.id, status="draft")
    db.add(series)
    db.commit()
    db.refresh(series)

    response = client.post(
        f"/api/image-series/{series.id}/frames",
        json={"prompt": "A new branch frame prompt"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["width"] == 1360
    assert payload["height"] == 768


@patch("app.routes.narration_images.generate_narration_image_series")
def test_regenerate_frame_resets_descendants(mock_task, client, db, tmp_path):
    project = _make_narration_project(db)
    segment = _make_segment(db, project)
    series = NarrationImageSeries(
        segment_id=segment.id,
        status=NarrationImageSeriesStatus.COMPLETED.value,
    )
    db.add(series)
    db.flush()

    root_path = tmp_path / "root.png"
    child_path = tmp_path / "child.png"
    root_path.write_bytes(b"root")
    child_path.write_bytes(b"child")

    root = NarrationImageFrame(
        series_id=series.id,
        prompt="Root",
        mode=NarrationImageGenerationMode.TEXT_TO_IMAGE.value,
        status=NarrationImageFrameStatus.COMPLETED.value,
        step_order=1,
        invokeai_generated_image_name="root_image",
        output_image_path=str(root_path),
    )
    db.add(root)
    db.flush()
    child = NarrationImageFrame(
        series_id=series.id,
        parent_frame_id=root.id,
        prompt="Child",
        mode=NarrationImageGenerationMode.IMAGE_TO_IMAGE.value,
        status=NarrationImageFrameStatus.COMPLETED.value,
        step_order=2,
        invokeai_reference_image_name="root_image",
        invokeai_generated_image_name="child_image",
        output_image_path=str(child_path),
    )
    db.add(child)
    db.commit()
    db.refresh(series)

    response = client.post(
        f"/api/image-series/{series.id}/frames/{root.id}/regenerate",
        json={"include_descendants": True, "auto_generate": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == NarrationImageSeriesStatus.QUEUED.value
    assert mock_task.delay.call_count == 1

    db.refresh(root)
    db.refresh(child)
    assert root.status == NarrationImageFrameStatus.PENDING.value
    assert root.output_image_path is None
    assert child.status == NarrationImageFrameStatus.PENDING.value
    assert child.output_image_path is None
    assert not root_path.exists()
    assert not child_path.exists()


def test_delete_series_removes_rows_and_files(client, db, tmp_path):
    project = _make_narration_project(db)
    segment = _make_segment(db, project)
    series = NarrationImageSeries(segment_id=segment.id, status="draft")
    db.add(series)
    db.flush()
    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"image")
    frame = NarrationImageFrame(
        series_id=series.id,
        prompt="Frame",
        mode=NarrationImageGenerationMode.TEXT_TO_IMAGE.value,
        status=NarrationImageFrameStatus.COMPLETED.value,
        step_order=1,
        output_image_path=str(image_path),
    )
    db.add(frame)
    db.commit()

    response = client.delete(f"/api/image-series/{series.id}")
    assert response.status_code == 204
    assert not image_path.exists()

    in_db = (
        db.query(NarrationImageSeries)
        .filter(NarrationImageSeries.id == series.id)
        .first()
    )
    assert in_db is None
