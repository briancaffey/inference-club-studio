def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_docs(client):
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc(client):
    response = client.get("/redoc")
    assert response.status_code == 200
