from app.models.service_config import ServiceConfig, ServiceConfigAudit
from app.services.config_manager import ConfigManager, ConfigManagerError


def _clear(db):
    db.query(ServiceConfigAudit).delete()
    db.query(ServiceConfig).delete()
    db.commit()


def test_get_config_falls_back_to_env(db):
    _clear(db)
    manager = ConfigManager(db)

    config = manager.get_config("invokeai")

    assert "url" in config


def test_update_config_creates_row_and_audit(db):
    _clear(db)
    manager = ConfigManager(db)

    manager.update_config(
        service_key="invokeai",
        updates={"url": "http://invokeai.test:1234", "poll_interval": 1.5},
        updated_by="tester",
    )

    row = (
        db.query(ServiceConfig).filter(ServiceConfig.service_key == "invokeai").first()
    )
    assert row is not None
    assert row.config["url"] == "http://invokeai.test:1234"
    assert row.config["poll_interval"] == 1.5
    assert row.updated_by == "tester"

    audits = (
        db.query(ServiceConfigAudit)
        .filter(ServiceConfigAudit.service_key == "invokeai")
        .all()
    )
    assert len(audits) == 1
    assert set(audits[0].changed_fields) == {"url", "poll_interval"}


def test_update_config_validation_rejects_bad_values(db):
    _clear(db)
    manager = ConfigManager(db)

    try:
        manager.update_config(
            service_key="invokeai",
            updates={"poll_interval": -1.0},
        )
    except ConfigManagerError:
        pass
    else:  # pragma: no cover - fail the test if no error
        raise AssertionError("ConfigManagerError not raised for invalid update")


def test_update_config_second_update_merges(db):
    _clear(db)
    manager = ConfigManager(db)

    manager.update_config(
        service_key="comfyui",
        updates={"url": "http://comfy.test"},
    )
    manager.update_config(
        service_key="comfyui",
        updates={"poll_interval": 10.0},
    )

    config = manager.get_config("comfyui")
    assert config["url"] == "http://comfy.test"
    assert config["poll_interval"] == 10.0


def test_api_list_all_configs(client, db):
    _clear(db)
    response = client.get("/api/v1/service-configs/")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "invokeai",
        "comfyui",
        "studio_voice",
        "llm",
        "dia",
        "magpie",
        "stt",
        "flux2_klein",
        "openai_image",
        "image_generation",
    }
    assert "schema_fields" in body["invokeai"]
    assert "url" in body["invokeai"]["schema_fields"]


def test_api_get_unknown_service_returns_404(client):
    response = client.get("/api/v1/service-configs/not_a_real_service")
    assert response.status_code == 404


def test_api_patch_persists_and_returns_config(client, db):
    _clear(db)
    response = client.patch(
        "/api/v1/service-configs/comfyui",
        json={"updates": {"url": "http://new-comfy:9000"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["service_key"] == "comfyui"
    assert body["config"]["url"] == "http://new-comfy:9000"
    assert body["source"] == "database"


def test_api_patch_rejects_invalid_update(client, db):
    _clear(db)
    response = client.patch(
        "/api/v1/service-configs/invokeai",
        json={"updates": {"poll_interval": -5}},
    )
    assert response.status_code == 400


def test_api_audit_history_returns_entries(client, db):
    _clear(db)
    client.patch(
        "/api/v1/service-configs/comfyui",
        json={"updates": {"url": "http://first"}},
    )
    client.patch(
        "/api/v1/service-configs/comfyui",
        json={"updates": {"url": "http://second"}},
    )

    response = client.get("/api/v1/service-configs/audit/comfyui")
    assert response.status_code == 200
    body = response.json()
    assert body["service_key"] == "comfyui"
    assert len(body["audits"]) == 2
    assert body["audits"][0]["new_config"]["url"] == "http://second"
