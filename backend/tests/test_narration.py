from app.models.project import Project


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
