from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.service_configs import SERVICE_CONFIG_SCHEMAS
from app.services.config_manager import ConfigManager, ConfigManagerError

router = APIRouter(prefix="/api/v1/service-configs", tags=["service-configs"])


class ConfigUpdateRequest(BaseModel):
    """Request to update service configuration."""

    updates: dict[str, Any] = Field(..., description="Config fields to update")
    validate: bool = True


class ConfigResponse(BaseModel):
    """Response containing current configuration."""

    service_key: str
    config: dict[str, Any]
    source: str


@router.get("/{service_key}", response_model=ConfigResponse)
def get_service_config(
    service_key: str,
    db: Session = Depends(get_db),
):
    """Get current configuration for a service."""
    if service_key not in SERVICE_CONFIG_SCHEMAS:
        raise HTTPException(status_code=404, detail="Unknown service")

    manager = ConfigManager(db)
    config = manager.get_config(service_key)

    return ConfigResponse(
        service_key=service_key,
        config=config,
        source="database" if config else "environment",
    )


@router.patch("/{service_key}", response_model=ConfigResponse)
def update_service_config(
    service_key: str,
    request: ConfigUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update configuration for a service."""
    if service_key not in SERVICE_CONFIG_SCHEMAS:
        raise HTTPException(status_code=404, detail="Unknown service")

    manager = ConfigManager(db)

    try:
        manager.update_config(
            service_key=service_key,
            updates=request.updates,
            validate=request.validate,
        )
    except ConfigManagerError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return get_service_config(service_key, db)


@router.get("/")
def list_all_configs(db: Session = Depends(get_db)):
    """List all service configurations."""
    manager = ConfigManager(db)
    result = {}

    for key in SERVICE_CONFIG_SCHEMAS.keys():
        config = manager.get_config(key)
        result[key] = {
            "config": config,
            "schema_fields": list(SERVICE_CONFIG_SCHEMAS[key].model_fields.keys()),
        }

    return result


@router.get("/audit/{service_key}")
def get_config_audit(
    service_key: str,
    db: Session = Depends(get_db),
):
    """Get audit history for a service configuration."""
    from app.models.service_config import ServiceConfigAudit

    if service_key not in SERVICE_CONFIG_SCHEMAS:
        raise HTTPException(status_code=404, detail="Unknown service")

    audits = (
        db.query(ServiceConfigAudit)
        .filter(ServiceConfigAudit.service_key == service_key)
        .order_by(ServiceConfigAudit.created_at.desc())
        .limit(50)
        .all()
    )

    return {
        "service_key": service_key,
        "audits": [
            {
                "id": a.id,
                "changed_fields": a.changed_fields,
                "old_config": a.old_config,
                "new_config": a.new_config,
                "updated_by": a.updated_by,
                "created_at": a.created_at.isoformat(),
            }
            for a in audits
        ],
    }
