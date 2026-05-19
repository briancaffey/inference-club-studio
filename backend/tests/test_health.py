from app.clients.comfyui.client import ComfyUIClient
from app.clients.flux2_klein.client import Flux2KleinClient
from app.clients.invokeai.client import InvokeAIClient
from app.clients.openai_image.client import OpenAIImageClient
from app.routes import health as health_routes


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


def test_services_health_all_healthy(client, monkeypatch):
    async def _healthy(self):
        return True

    async def _healthy_http(base_url: str, paths: tuple[str, ...]):
        return True, None

    monkeypatch.setattr(InvokeAIClient, "check_health", _healthy)
    monkeypatch.setattr(ComfyUIClient, "check_health", _healthy)
    monkeypatch.setattr(Flux2KleinClient, "check_health", _healthy)
    monkeypatch.setattr(OpenAIImageClient, "check_health", _healthy)
    monkeypatch.setattr(health_routes, "_check_http_reachable", _healthy_http)

    response = client.get("/api/v1/services/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["healthy_services"] == 9
    assert body["total_services"] == 9
    assert len(body["services"]) == 9
    assert all(service["healthy"] is True for service in body["services"])
    assert {s["key"] for s in body["services"]} == {
        "llm",
        "invokeai",
        "comfyui",
        "dia",
        "magpie",
        "stt",
        "studio_voice",
        "flux2_klein",
        "openai_image",
    }


def test_services_health_degraded(client, monkeypatch):
    async def _healthy(self):
        return True

    async def _unhealthy(self):
        return False

    async def _healthy_http(base_url: str, paths: tuple[str, ...]):
        return True, None

    monkeypatch.setattr(InvokeAIClient, "check_health", _healthy)
    monkeypatch.setattr(ComfyUIClient, "check_health", _unhealthy)
    monkeypatch.setattr(Flux2KleinClient, "check_health", _healthy)
    monkeypatch.setattr(OpenAIImageClient, "check_health", _healthy)
    monkeypatch.setattr(health_routes, "_check_http_reachable", _healthy_http)

    response = client.get("/api/v1/services/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["healthy_services"] == 8
    assert body["total_services"] == 9
    assert any(service["healthy"] is False for service in body["services"])
