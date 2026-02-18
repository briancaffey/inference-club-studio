from unittest.mock import patch

from app.models.cut import Cut, CutStatus
from app.models.generation import Generation, GenerationStatus
from app.models.project import Project
from app.models.take import Take, TakeStatus


def _make_project(db, name="Test Project"):
    project = Project(name=name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_cut(db, project, status=CutStatus.READY.value):
    cut = Cut(
        project_id=project.id,
        order=0,
        original_filename="cut_01.mp4",
        file_path=f"/app/media/{project.id}/cuts/cut_01.mp4",
        file_size=1024,
        status=status,
    )
    db.add(cut)
    db.commit()
    db.refresh(cut)
    return cut


def _make_generation(db, cut, status=GenerationStatus.COMPLETED.value):
    generation = Generation(
        cut_id=cut.id,
        prompt="test style",
        status=status,
        output_image_path="/app/media/test/output.png",
    )
    db.add(generation)
    db.commit()
    db.refresh(generation)
    return generation


def _make_take(db, generation, prompt="test video prompt"):
    take = Take(
        generation_id=generation.id,
        prompt=prompt,
        status=TakeStatus.COMPLETED.value,
    )
    db.add(take)
    db.commit()
    db.refresh(take)
    return take


def _url(project_id, cut_id, generation_id, take_id=None):
    base = (
        f"/api/v1/projects/{project_id}/cuts/{cut_id}"
        f"/generations/{generation_id}/takes"
    )
    if take_id:
        return f"{base}/{take_id}"
    return base


@patch("app.routes.takes.generate_video_take")
def test_create_take(mock_task, client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut)

    resp = client.post(
        _url(project.id, cut.id, generation.id),
        json={"prompt": "a cinematic scene"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["prompt"] == "a cinematic scene"
    assert data["width"] == 640
    assert data["height"] == 448
    assert data["frame_count"] == 122
    assert data["seed"] == -1
    assert data["status"] == "pending"
    assert mock_task.delay.call_count == 1


@patch("app.routes.takes.generate_video_take")
def test_create_take_custom_params(mock_task, client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut)

    resp = client.post(
        _url(project.id, cut.id, generation.id),
        json={
            "prompt": "test",
            "width": 512,
            "height": 320,
            "frame_count": 60,
            "seed": 42,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["width"] == 512
    assert data["height"] == 320
    assert data["frame_count"] == 60
    assert data["seed"] == 42


@patch("app.routes.takes.generate_video_take")
def test_create_take_generation_not_completed(mock_task, client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut, status=GenerationStatus.PENDING.value)

    resp = client.post(
        _url(project.id, cut.id, generation.id),
        json={"prompt": "test"},
    )
    assert resp.status_code == 400
    assert "completed" in resp.json()["detail"].lower()
    assert mock_task.delay.call_count == 0


def test_list_takes(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut)
    _make_take(db, generation, prompt="take 1")
    _make_take(db, generation, prompt="take 2")

    resp = client.get(_url(project.id, cut.id, generation.id))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_get_take(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut)
    take = _make_take(db, generation, prompt="my take")

    resp = client.get(_url(project.id, cut.id, generation.id, take.id))
    assert resp.status_code == 200
    assert resp.json()["prompt"] == "my take"


def test_get_take_not_found(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut)

    resp = client.get(
        _url(
            project.id,
            cut.id,
            generation.id,
            "00000000-0000-0000-0000-000000000000",
        )
    )
    assert resp.status_code == 404


def test_delete_take(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut)
    take = _make_take(db, generation)

    resp = client.delete(_url(project.id, cut.id, generation.id, take.id))
    assert resp.status_code == 204

    resp = client.get(_url(project.id, cut.id, generation.id))
    assert len(resp.json()) == 0


def test_delete_take_not_found(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut)

    resp = client.delete(
        _url(
            project.id,
            cut.id,
            generation.id,
            "00000000-0000-0000-0000-000000000000",
        )
    )
    assert resp.status_code == 404


def test_create_take_project_not_found(client, db):
    resp = client.post(
        _url(
            "00000000-0000-0000-0000-000000000000",
            "00000000-0000-0000-0000-000000000000",
            "00000000-0000-0000-0000-000000000000",
        ),
        json={"prompt": "test"},
    )
    assert resp.status_code == 404


def test_create_take_generation_not_found(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.post(
        _url(
            project.id,
            cut.id,
            "00000000-0000-0000-0000-000000000000",
        ),
        json={"prompt": "test"},
    )
    assert resp.status_code == 404
