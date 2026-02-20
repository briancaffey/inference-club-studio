from app.models.project import Project


def test_create_project(client):
    resp = client.post("/api/v1/projects", json={"name": "Test Project"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Project"
    assert data["project_type"] == "video_to_video"
    assert data["cut_count"] == 0
    assert data["segment_count"] == 0
    assert "id" in data


def test_create_project_with_description(client):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "My Film", "description": "A great film"},
    )
    assert resp.status_code == 201
    assert resp.json()["description"] == "A great film"


def test_create_narration_project(client):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "Narration Project", "project_type": "narration"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["project_type"] == "narration"
    assert data["cut_count"] == 0
    assert data["segment_count"] == 0


def test_list_projects_empty(client):
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_projects(client, db):
    project_a = Project(name="Project A")
    project_b = Project(name="Project B")
    db.add(project_a)
    db.add(project_b)
    db.commit()
    db.refresh(project_a)
    db.refresh(project_b)

    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert str(project_a.id) in ids
    assert str(project_b.id) in ids


def test_get_project(client, db):
    project = Project(name="Detail Test")
    db.add(project)
    db.commit()
    db.refresh(project)

    resp = client.get(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Test"
    assert data["project_type"] == "video_to_video"
    assert data["segment_count"] == 0
    assert data["cuts"] == []


def test_get_project_not_found(client):
    resp = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_update_project(client, db):
    project = Project(name="Old Name")
    db.add(project)
    db.commit()
    db.refresh(project)

    resp = client.patch(
        f"/api/v1/projects/{project.id}",
        json={"name": "New Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_delete_project(client, db):
    project = Project(name="To Delete")
    db.add(project)
    db.commit()
    db.refresh(project)

    resp = client.delete(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 404
