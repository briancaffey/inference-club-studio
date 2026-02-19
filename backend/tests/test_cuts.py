import io
from unittest.mock import patch

from app.models.cut import Cut, CutStatus
from app.models.project import Project


def _make_project(db, name="Test Project"):
    project = Project(name=name)
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


def _make_cut(db, project, order=0, filename="cut_01.mp4"):
    cut = Cut(
        project_id=project.id,
        order=order,
        original_filename=filename,
        file_path=f"/app/media/{project.id}/cuts/{filename}",
        file_size=1024,
        status=CutStatus.READY.value,
    )
    db.add(cut)
    db.commit()
    db.refresh(cut)
    return cut


@patch("app.routes.cuts.process_cut_metadata")
def test_upload_cuts(mock_task, client, db, tmp_path):
    project = _make_project(db)

    file_content = b"fake video content"
    files = [
        ("files", ("cut_01.mp4", io.BytesIO(file_content), "video/mp4")),
        ("files", ("cut_02.mp4", io.BytesIO(file_content), "video/mp4")),
    ]

    resp = client.post(f"/api/v1/projects/{project.id}/cuts", files=files)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["uploaded"]) == 2
    assert data["uploaded"][0]["order"] == 0
    assert data["uploaded"][1]["order"] == 1
    assert mock_task.delay.call_count == 2


def test_list_cuts(client, db):
    project = _make_project(db)
    _make_cut(db, project, order=0, filename="cut_01.mp4")
    _make_cut(db, project, order=1, filename="cut_02.mp4")

    resp = client.get(f"/api/v1/projects/{project.id}/cuts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["order"] == 0
    assert data[1]["order"] == 1


def test_get_cut(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.get(f"/api/v1/projects/{project.id}/cuts/{cut.id}")
    assert resp.status_code == 200
    assert resp.json()["original_filename"] == "cut_01.mp4"


def test_get_cut_not_found(client, db):
    project = _make_project(db)

    resp = client.get(
        f"/api/v1/projects/{project.id}/cuts/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


def test_delete_cut_renumbers(client, db):
    project = _make_project(db)
    _make_cut(db, project, order=0, filename="cut_01.mp4")
    cut1 = _make_cut(db, project, order=1, filename="cut_02.mp4")
    _make_cut(db, project, order=2, filename="cut_03.mp4")

    resp = client.delete(f"/api/v1/projects/{project.id}/cuts/{cut1.id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/projects/{project.id}/cuts")
    data = resp.json()
    assert len(data) == 2
    assert data[0]["order"] == 0
    assert data[1]["order"] == 1


def test_reorder_cuts(client, db):
    project = _make_project(db)
    cut0 = _make_cut(db, project, order=0, filename="cut_01.mp4")
    cut1 = _make_cut(db, project, order=1, filename="cut_02.mp4")
    cut2 = _make_cut(db, project, order=2, filename="cut_03.mp4")

    # Reverse order
    resp = client.put(
        f"/api/v1/projects/{project.id}/cuts/reorder",
        json={"cut_ids": [str(cut2.id), str(cut1.id), str(cut0.id)]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["id"] == str(cut2.id)
    assert data[0]["order"] == 0
    assert data[2]["id"] == str(cut0.id)
    assert data[2]["order"] == 2


def test_reorder_cuts_missing_ids(client, db):
    project = _make_project(db)
    cut0 = _make_cut(db, project, order=0, filename="cut_01.mp4")
    _make_cut(db, project, order=1, filename="cut_02.mp4")

    resp = client.put(
        f"/api/v1/projects/{project.id}/cuts/reorder",
        json={"cut_ids": [str(cut0.id)]},
    )
    assert resp.status_code == 400


def test_upload_to_nonexistent_project(client):
    file_content = b"fake video content"
    files = [("files", ("cut_01.mp4", io.BytesIO(file_content), "video/mp4"))]

    resp = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/cuts",
        files=files,
    )
    assert resp.status_code == 404


def test_upload_cuts_to_narration_project_returns_400(client, db):
    project = _make_narration_project(db)
    file_content = b"fake video content"
    files = [("files", ("cut_01.mp4", io.BytesIO(file_content), "video/mp4"))]

    resp = client.post(f"/api/v1/projects/{project.id}/cuts", files=files)
    assert resp.status_code == 400
