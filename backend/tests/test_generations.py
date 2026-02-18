from unittest.mock import patch

from app.models.cut import Cut, CutStatus
from app.models.generation import Generation, GenerationStatus
from app.models.project import Project


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


def _make_generation(db, cut, prompt="test prompt"):
    generation = Generation(
        cut_id=cut.id,
        prompt=prompt,
        status=GenerationStatus.COMPLETED.value,
    )
    db.add(generation)
    db.commit()
    db.refresh(generation)
    return generation


def _url(project_id, cut_id, generation_id=None):
    base = f"/api/v1/projects/{project_id}/cuts/{cut_id}/generations"
    if generation_id:
        return f"{base}/{generation_id}"
    return base


@patch("app.routes.generations.generate_style_transfer")
def test_create_generation(mock_task, client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.post(
        _url(project.id, cut.id),
        json={"prompt": "watercolor painting style"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["prompt"] == "watercolor painting style"
    assert data["width"] == 1024
    assert data["height"] == 1024
    assert data["num_steps"] == 16
    assert data["cfg_scale"] == 1.0
    assert data["seed"] == -1
    assert data["status"] == "pending"
    assert mock_task.delay.call_count == 1


@patch("app.routes.generations.generate_style_transfer")
def test_create_generation_custom_params(mock_task, client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.post(
        _url(project.id, cut.id),
        json={
            "prompt": "oil painting",
            "width": 512,
            "height": 768,
            "num_steps": 24,
            "cfg_scale": 2.5,
            "seed": 42,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["width"] == 512
    assert data["height"] == 768
    assert data["num_steps"] == 24
    assert data["cfg_scale"] == 2.5
    assert data["seed"] == 42


@patch("app.routes.generations.generate_style_transfer")
def test_create_generation_cut_not_ready(mock_task, client, db):
    project = _make_project(db)
    cut = _make_cut(db, project, status=CutStatus.UPLOADED.value)

    resp = client.post(
        _url(project.id, cut.id),
        json={"prompt": "test"},
    )
    assert resp.status_code == 400
    assert "ready" in resp.json()["detail"].lower()
    assert mock_task.delay.call_count == 0


def test_list_generations(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    _make_generation(db, cut, prompt="prompt 1")
    _make_generation(db, cut, prompt="prompt 2")

    resp = client.get(_url(project.id, cut.id))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_get_generation(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut, prompt="my prompt")

    resp = client.get(_url(project.id, cut.id, generation.id))
    assert resp.status_code == 200
    assert resp.json()["prompt"] == "my prompt"


def test_get_generation_not_found(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.get(_url(project.id, cut.id, "00000000-0000-0000-0000-000000000000"))
    assert resp.status_code == 404


def test_delete_generation(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)
    generation = _make_generation(db, cut)

    resp = client.delete(_url(project.id, cut.id, generation.id))
    assert resp.status_code == 204

    resp = client.get(_url(project.id, cut.id))
    assert len(resp.json()) == 0


def test_delete_generation_not_found(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.delete(
        _url(project.id, cut.id, "00000000-0000-0000-0000-000000000000")
    )
    assert resp.status_code == 404


def test_create_generation_project_not_found(client, db):
    resp = client.post(
        _url(
            "00000000-0000-0000-0000-000000000000",
            "00000000-0000-0000-0000-000000000000",
        ),
        json={"prompt": "test"},
    )
    assert resp.status_code == 404


def test_create_generation_cut_not_found(client, db):
    project = _make_project(db)
    resp = client.post(
        _url(project.id, "00000000-0000-0000-0000-000000000000"),
        json={"prompt": "test"},
    )
    assert resp.status_code == 404
