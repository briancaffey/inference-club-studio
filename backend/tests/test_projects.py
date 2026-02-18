from app.models.project import Project


def test_create_project(client):
    resp = client.post("/api/v1/projects", json={"name": "Test Project"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Project"
    assert data["cut_count"] == 0
    assert "id" in data


def test_create_project_with_description(client):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "My Film", "description": "A great film"},
    )
    assert resp.status_code == 201
    assert resp.json()["description"] == "A great film"


def test_list_projects_empty(client):
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_projects(client, db):
    db.add(Project(name="Project A"))
    db.add(Project(name="Project B"))
    db.commit()

    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_get_project(client, db):
    project = Project(name="Detail Test")
    db.add(project)
    db.commit()
    db.refresh(project)

    resp = client.get(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Test"
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
