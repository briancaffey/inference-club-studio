import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.service_config import ServiceConfig, ServiceConfigAudit
from app.schemas.service_configs import SERVICE_CONFIG_SCHEMAS

logger = logging.getLogger(__name__)


class ConfigManagerError(Exception):
    """Raised when config operations fail."""

    pass


class ConfigManager:
    """Centralized service configuration manager with database backend."""

    def __init__(self, db: Session):
        self.db = db

    def get_config(self, service_key: str) -> dict[str, Any]:
        """
        Get active configuration for a service.

        Falls back to env-based settings if no DB config exists.
        """
        config = (
            self.db.query(ServiceConfig)
            .filter(
                ServiceConfig.service_key == service_key,
                ServiceConfig.is_active == True,
            )
            .first()
        )

        if config:
            return config.config

        logger.warning(
            "No database config found for %s, falling back to env vars",
            service_key,
        )
        return self._get_env_fallback(service_key)

    def get_config_typed(self, service_key: str) -> Any:
        """
        Get configuration validated against the service's schema.

        Raises ConfigManagerError if validation fails.
        """
        raw_config = self.get_config(service_key)

        if service_key not in SERVICE_CONFIG_SCHEMAS:
            raise ConfigManagerError(f"No schema defined for service: {service_key}")

        schema = SERVICE_CONFIG_SCHEMAS[service_key]

        try:
            return schema(**raw_config)
        except ValidationError as e:
            raise ConfigManagerError(f"Config validation failed: {e}") from e

    def update_config(
        self,
        service_key: str,
        updates: dict[str, Any],
        updated_by: Optional[str] = None,
        validate: bool = True,
    ) -> ServiceConfig:
        """
        Update configuration for a service.

        Merges updates with existing config, validates if requested,
        and creates audit log entry.
        """
        current_config = self.get_config(service_key)
        new_config = {**current_config, **updates}

        if validate and service_key in SERVICE_CONFIG_SCHEMAS:
            schema = SERVICE_CONFIG_SCHEMAS[service_key]
            try:
                schema(**new_config)
            except ValidationError as e:
                raise ConfigManagerError(f"Invalid config: {e}") from e

        db_config = (
            self.db.query(ServiceConfig)
            .filter(ServiceConfig.service_key == service_key)
            .first()
        )

        old_config = db_config.config if db_config else None

        if db_config:
            db_config.config = new_config
            db_config.updated_at = datetime.utcnow()
            db_config.updated_by = updated_by
        else:
            db_config = ServiceConfig(
                service_key=service_key,
                config=new_config,
                is_active=True,
                updated_by=updated_by,
            )
            self.db.add(db_config)

        changed_fields = list(updates.keys())
        audit = ServiceConfigAudit(
            service_key=service_key,
            old_config=old_config,
            new_config=new_config,
            changed_fields=changed_fields,
            updated_by=updated_by,
        )
        self.db.add(audit)

        self.db.commit()
        self.db.refresh(db_config)

        logger.info("Updated config for %s: fields=%s", service_key, changed_fields)

        return db_config

    def disable_config(self, service_key: str, updated_by: Optional[str] = None):
        """Soft-disable a configuration (falls back to env vars)."""
        config = (
            self.db.query(ServiceConfig)
            .filter(ServiceConfig.service_key == service_key)
            .first()
        )

        if not config:
            raise ConfigManagerError(f"No config found for {service_key}")

        old_config = config.config
        config.is_active = False
        config.updated_at = datetime.utcnow()
        config.updated_by = updated_by

        audit = ServiceConfigAudit(
            service_key=service_key,
            old_config=old_config,
            new_config=None,
            changed_fields=["is_active"],
            updated_by=updated_by,
        )
        self.db.add(audit)

        self.db.commit()

    def _get_env_fallback(self, service_key: str) -> dict[str, Any]:
        """
        Extract config from current env-based settings.

        This is used during migration and as fallback.
        """
        fallbacks = {
            "invokeai": {
                "url": settings.invokeai_url,
                "board_id": settings.invokeai_board_id,
            },
            "comfyui": {
                "url": settings.comfyui_url,
            },
            "studio_voice": {
                "url": settings.studio_voice_url,
                "health_url": settings.studio_voice_health_url,
                "grpc_target": settings.studio_voice_grpc_target,
                "model_type": settings.studio_voice_model_type,
                "input_sample_rate": settings.studio_voice_input_sample_rate,
                "auto_clean": settings.studio_voice_auto_clean,
                "enhance_path": settings.studio_voice_enhance_path,
            },
            "llm": {
                "base_url": settings.openai_base_url,
                "model": settings.openai_model,
                "api_key": settings.openai_api_key or None,
            },
            "dia": {
                "url": settings.dia_url,
            },
            "magpie": {
                "url": settings.magpie_url,
            },
            "stt": {
                "provider": "openai",
                "base_url": settings.stt_url,
                "model": "Qwen/Qwen3-ASR-1.7B",
                "api_key": None,
                "language": None,
            },
            "flux2_klein": {
                "url": settings.flux2_klein_url,
                "model": settings.flux2_klein_model,
                "api_key": settings.flux2_klein_api_key or None,
            },
            "openai_image": {
                "base_url": settings.openai_image_base_url,
                "model": settings.openai_image_model,
                "api_key": settings.openai_image_api_key or None,
            },
            "image_generation": {
                "provider": settings.image_provider,
            },
        }

        return fallbacks.get(service_key, {})
