# Dynamic Service Configuration Management Plan

## Overview

This document outlines a plan to migrate from static `.env` file-based configuration to a dynamic, database-backed configuration system that allows updating service endpoints and settings without requiring Docker restarts.

## Current State Analysis

### Existing Services
The system currently manages the following external services via environment variables:

1. **LLM/Text Generation**
   - `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`
   - `GROQ_API_KEY`

2. **Image Generation**
   - `INVOKEAI_URL`, `INVOKEAI_BOARD_ID`
   - `COMFYUI_URL`

3. **Video/Audio Services**
   - `DIA_URL` (TTS)
   - `MAGPIE_URL` (TTS)
   - `STT_URL` (Speech-to-Text)
   - `STUDIO_VOICE_URL`, `STUDIO_VOICE_HEALTH_URL`, `STUDIO_VOICE_GRPC_TARGET`
   - `STUDIO_VOICE_MODEL_TYPE`, `STUDIO_VOICE_INPUT_SAMPLE_RATE`, `STUDIO_VOICE_AUTO_CLEAN`
   - `STUDIO_VOICE_ENHANCE_PATH`

4. **Vision Services**
   - `QWEN_VL_URL`

### Current Architecture
- Configuration loaded via Pydantic Settings from `.env` at startup
- Values passed to Docker containers via `docker-compose.yml` environment variables
- Clients instantiate with config values or fall back to global settings
- Changes require: update `.env` → restart Docker containers

## Goals

1. **Dynamic Updates**: Change service configurations without Docker restarts
2. **Type Safety**: Maintain Python type hints for each service's configuration schema
3. **Flexibility**: Support different configuration structures per service
4. **Backward Compatibility**: Continue supporting `.env` as fallback during migration
5. **Auditability**: Track configuration changes in the database
6. **Validation**: Ensure config changes are valid before activation

## Proposed Architecture

### Database Schema

```python
# app/models/service_config.py

from datetime import datetime
from typing import Any
from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class ServiceConfig(Base):
    """Database-backed service configuration with JSONB flexibility."""
    
    __tablename__ = "service_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    service_key = Column(String(50), unique=True, nullable=False, index=True)
    # e.g., "invokeai", "comfyui", "studio_voice", "llm", etc.
    
    config = Column(JSONB, nullable=False, default=dict)
    # Flexible JSON storage for service-specific settings
    # Example: {"url": "...", "board_id": "...", "timeout": 300}
    
    is_active = Column(Boolean, default=True, nullable=False)
    # Soft-disable configs without deleting
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Optional: track which user/process made the change
    updated_by = Column(String(100), nullable=True)
```

### Configuration Change Audit Log

```python
# app/models/service_config_audit.py

class ServiceConfigAudit(Base):
    """Audit trail for configuration changes."""
    
    __tablename__ = "service_config_audits"
    
    id = Column(Integer, primary_key=True, index=True)
    service_key = Column(String(50), nullable=False, index=True)
    
    old_config = Column(JSONB, nullable=True)
    new_config = Column(JSONB, nullable=False)
    
    changed_fields = Column(JSONB, nullable=False)
    # List of fields that changed: ["url", "timeout"]
    
    updated_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### Pydantic Config Schemas (Type-Safe JSON Validation)

Each service gets a dedicated schema defining its expected configuration structure:

```python
# app/schemas/service_configs.py

from pydantic import BaseModel, HttpUrl, Field
from typing import Optional


class InvokeAIConfig(BaseModel):
    """InvokeAI service configuration schema."""
    url: str = Field(..., description="InvokeAPI base URL")
    board_id: Optional[str] = None
    poll_interval: float = Field(default=2.0, ge=0.1)
    timeout: float = Field(default=300.0, ge=1.0)
    max_retries: int = Field(default=3, ge=0)


class ComfyUIConfig(BaseModel):
    """ComfyUI service configuration schema."""
    url: str = Field(..., description="ComfyUI base URL")
    poll_interval: float = Field(default=5.0, ge=0.1)
    timeout: float = Field(default=600.0, ge=1.0)


class StudioVoiceConfig(BaseModel):
    """NVIDIA Studio Voice configuration schema."""
    url: str = Field(..., description="Studio Voice HTTP base URL")
    health_url: Optional[str] = None
    grpc_target: Optional[str] = None
    model_type: str = Field(default="48k-hq")
    input_sample_rate: int = Field(default=48000, ge=16000)
    auto_clean: bool = True
    enhance_path: Optional[str] = None


class LLMConfig(BaseModel):
    """LLM/OpenAI-compatible API configuration schema."""
    base_url: str = Field(..., description="OpenAI-compatible API base URL")
    model: str = Field(default="gpt-4", description="Default model name")
    api_key: Optional[str] = None


class TTSConfig(BaseModel):
    """Generic TTS service configuration."""
    url: str = Field(..., description="TTS service base URL")
    timeout: float = Field(default=60.0, ge=1.0)


# Service-specific schemas for different TTS backends
class DIAConfig(TTSConfig):
    pass  # Extend with DIA-specific fields if needed


class MagpieConfig(TTSConfig):
    voices: list[str] = []  # Optional cached voice list


class STTConfig(BaseModel):
    """Speech-to-text service configuration."""
    url: str = Field(..., description="STT service base URL")
    timeout: float = Field(default=120.0, ge=1.0)


class QwenVLConfig(BaseModel):
    """Qwen-VL vision language model configuration."""
    url: str = Field(..., description="Qwen-VL base URL")
    timeout: float = Field(default=60.0, ge=1.0)


# Registry mapping service keys to their schemas
SERVICE_CONFIG_SCHEMAS: dict[str, type[BaseModel]] = {
    "invokeai": InvokeAIConfig,
    "comfyui": ComfyUIConfig,
    "studio_voice": StudioVoiceConfig,
    "llm": LLMConfig,
    "dia": DIAConfig,
    "magpie": MagpieConfig,
    "stt": STTConfig,
    "qwen_vl": QwenVLConfig,
}
```

### Configuration Manager Service

Central service for reading/writing configs with validation:

```python
# app/services/config_manager.py

import logging
from datetime import datetime
from typing import Any, Optional
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.models.service_config import ServiceConfig
from app.models.service_config_audit import ServiceConfigAudit
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
        # Try database first
        config = self.db.query(ServiceConfig).filter(
            ServiceConfig.service_key == service_key,
            ServiceConfig.is_active == True
        ).first()
        
        if config:
            return config.config
        
        # Fallback to environment-based settings
        logger.warning(
            "No database config found for %s, falling back to env vars",
            service_key
        )
        return self._get_env_fallback(service_key)
    
    def get_config_typed(self, service_key: str) -> BaseModel:
        """
        Get configuration validated against the service's schema.
        
        Raises ConfigManagerError if validation fails.
        """
        raw_config = self.get_config(service_key)
        
        if service_key not in SERVICE_CONFIG_SCHEMAS:
            raise ConfigManagerError(
                f"No schema defined for service: {service_key}"
            )
        
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
        validate: bool = True
    ) -> ServiceConfig:
        """
        Update configuration for a service.
        
        Merges updates with existing config, validates if requested,
        and creates audit log entry.
        """
        # Get current config (from DB or env fallback)
        current_config = self.get_config(service_key)
        
        # Merge updates
        new_config = {**current_config, **updates}
        
        # Validate against schema if requested
        if validate and service_key in SERVICE_CONFIG_SCHEMAS:
            schema = SERVICE_CONFIG_SCHEMAS[service_key]
            try:
                schema(**new_config)  # Validate but don't use result
            except ValidationError as e:
                raise ConfigManagerError(f"Invalid config: {e}") from e
        
        # Get or create ServiceConfig record
        db_config = self.db.query(ServiceConfig).filter(
            ServiceConfig.service_key == service_key
        ).first()
        
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
                updated_by=updated_by
            )
            self.db.add(db_config)
        
        # Create audit entry
        changed_fields = list(updates.keys())
        audit = ServiceConfigAudit(
            service_key=service_key,
            old_config=old_config,
            new_config=new_config,
            changed_fields=changed_fields,
            updated_by=updated_by
        )
        self.db.add(audit)
        
        self.db.commit()
        self.db.refresh(db_config)
        
        logger.info(
            "Updated config for %s: fields=%s",
            service_key, changed_fields
        )
        
        return db_config
    
    def disable_config(self, service_key: str, updated_by: Optional[str] = None):
        """Soft-disable a configuration (falls back to env vars)."""
        config = self.db.query(ServiceConfig).filter(
            ServiceConfig.service_key == service_key
        ).first()
        
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
            updated_by=updated_by
        )
        self.db.add(audit)
        
        self.db.commit()
    
    def _get_env_fallback(self, service_key: str) -> dict[str, Any]:
        """
        Extract config from current env-based settings.
        
        This is used during migration and as fallback.
        """
        from app.config import settings
        
        # Map each service to its env var equivalents
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
                "url": settings.stt_url,
            },
            "qwen_vl": {
                "url": settings.qwen_vl_url,
            },
        }
        
        return fallbacks.get(service_key, {})
```

### Updated Client Pattern

Clients should accept optional config dicts and fall back to settings:

```python
# Example: app/clients/invokeai/client.py (updated)

class InvokeAIClient:
    """Client for InvokeAI image generation service."""
    
    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        # Legacy params for backward compatibility
        url: Optional[str] = None,
        board_id: Optional[str] = None,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        max_retries: int = 3,
    ):
        if config is not None:
            # New pattern: use provided config dict
            self.url = config.get("url", settings.invokeai_url)
            self.board_id = config.get("board_id", settings.invokeai_board_id)
            self.poll_interval = config.get("poll_interval", poll_interval)
            self.timeout = config.get("timeout", timeout)
            self.max_retries = config.get("max_retries", max_retries)
        else:
            # Legacy pattern: use individual params or settings
            self.url = url or settings.invokeai_url
            self.board_id = board_id if board_id is not None else settings.invokeai_board_id
            self.poll_interval = poll_interval
            self.timeout = timeout
            self.max_retries = max_retries
```

### API Endpoints for Configuration Management

```python
# app/routes/service_configs.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Any

from app.db.session import get_db
from app.services.config_manager import ConfigManager, ConfigManagerError
from app.schemas.service_configs import SERVICE_CONFIG_SCHEMAS
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/service-configs", tags=["service-configs"])


class ConfigUpdateRequest(BaseModel):
    """Request to update service configuration."""
    updates: dict[str, Any] = Field(..., description="Config fields to update")
    validate: bool = True


class ConfigResponse(BaseModel):
    """Response containing current configuration."""
    service_key: str
    config: dict[str, Any]
    source: str  # "database" or "environment"


@router.get("/{service_key}", response_model=ConfigResponse)
def get_service_config(
    service_key: str,
    db: Session = Depends(get_db)
):
    """Get current configuration for a service."""
    if service_key not in SERVICE_CONFIG_SCHEMAS:
        raise HTTPException(status_code=404, detail="Unknown service")
    
    manager = ConfigManager(db)
    config = manager.get_config(service_key)
    
    return ConfigResponse(
        service_key=service_key,
        config=config,
        source="database" if config else "environment"
    )


@router.patch("/{service_key}", response_model=ConfigResponse)
def update_service_config(
    service_key: str,
    request: ConfigUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update configuration for a service."""
    if service_key not in SERVICE_CONFIG_SCHEMAS:
        raise HTTPException(status_code=404, detail="Unknown service")
    
    manager = ConfigManager(db)
    
    try:
        manager.update_config(
            service_key=service_key,
            updates=request.updates,
            validate=request.validate
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
            "schema_fields": list(SERVICE_CONFIG_SCHEMAS[key].model_fields.keys())
        }
    
    return result


@router.get("/audit/{service_key}")
def get_config_audit(
    service_key: str,
    db: Session = Depends(get_db)
):
    """Get audit history for a service configuration."""
    from app.models.service_config_audit import ServiceConfigAudit
    
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
                "created_at": a.created_at.isoformat()
            }
            for a in audits
        ]
    }
```

## Implementation Plan

### Phase 1: Database Schema & Models (Day 1)

1. Create `ServiceConfig` and `ServiceConfigAudit` models
2. Generate Alembic migration
3. Add models to `app/models/__init__.py`

**Files:**
- `app/models/service_config.py` (new)
- `app/models/service_config_audit.py` (new)
- `alembic/versions/{timestamp}_add_service_configs.py` (migration)

### Phase 2: Pydantic Schemas (Day 1)

1. Define schema for each service in `app/schemas/service_configs.py`
2. Create `SERVICE_CONFIG_SCHEMAS` registry
3. Add validation tests

**Files:**
- `app/schemas/service_configs.py` (new)
- `tests/test_service_config_schemas.py` (new)

### Phase 3: Config Manager Service (Day 2)

1. Implement `ConfigManager` class with CRUD operations
2. Add audit logging
3. Implement env fallback logic
4. Write unit tests

**Files:**
- `app/services/config_manager.py` (new)
- `tests/test_config_manager.py` (new)

### Phase 4: API Endpoints (Day 2)

1. Create router with GET/PATCH endpoints
2. Add authentication/authorization if needed
3. Integrate with existing `/api/v1` prefix
4. Write integration tests

**Files:**
- `app/routes/service_configs.py` (new)
- Update `app/main.py` to include new router
- `tests/test_service_config_routes.py` (new)

### Phase 5: Client Updates (Day 3)

Update each client to accept optional config dicts:

1. `InvokeAIClient` - add `config` param
2. `ComfyUIClient` - add `config` param  
3. `StudioVoiceClient` - add `config` param
4. `QwenVLClient` - add `config` param
5. Other clients as needed

**Files:**
- `app/clients/invokeai/client.py` (update)
- `app/clients/comfyui/client.py` (update)
- `app/clients/studio_voice/client.py` (update)
- `app/clients/qwen_vl/client.py` (update)

### Phase 6: Integration with Tasks/Routes (Day 3-4)

Update Celery tasks and routes to use ConfigManager:

```python
# Example task update
from app.db.session import get_db
from app.services.config_manager import ConfigManager

@app.celery_app.task
def generate_image_task(prompt: str):
    with get_db() as db:
        manager = ConfigManager(db)
        config = manager.get_config("invokeai")
        client = InvokeAIClient(config=config)
        # ... use client
```

### Phase 7: Migration & Testing (Day 4-5)

1. Seed initial configs from current `.env` values
2. Test dynamic updates via API
3. Verify clients pick up changes without restart
4. Load test configuration caching if needed

## Caching Strategy (Optional Optimization)

For high-performance scenarios, add Redis caching:

```python
# app/services/config_manager.py (with caching)

import redis
import json
from functools import lru_cache

class ConfigManager:
    def __init__(self, db: Session, cache_ttl: int = 300):
        self.db = db
        self.cache_ttl = cache_ttl
    
    def get_config(self, service_key: str) -> dict[str, Any]:
        # Check Redis cache first
        cache_key = f"service_config:{service_key}"
        cached = redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        # Fetch from DB (existing logic)
        config = self._fetch_from_db(service_key)
        
        # Cache result
        redis_client.setex(cache_key, self.cache_ttl, json.dumps(config))
        
        return config
    
    def update_config(self, service_key: str, updates: dict, ...):
        # Existing update logic...
        
        # Invalidate cache on update
        cache_key = f"service_config:{service_key}"
        redis_client.delete(cache_key)
```

## Rollout Strategy

### Week 1: Development & Testing
- Implement Phases 1-4 in development environment
- Run full test suite
- Manual testing of config updates via API

### Week 2: Gradual Migration
- Deploy to staging with both env and DB configs active
- Migrate one service at a time (start with InvokeAI)
- Monitor for issues, verify clients use DB configs

### Week 3: Full Production Rollout
- Migrate remaining services
- Update documentation
- Train team on new config management workflow

## Benefits

1. **No Downtime Updates**: Change endpoints/settings via API without restarts
2. **Type Safety**: Pydantic schemas catch invalid configs before activation
3. **Audit Trail**: Track who changed what and when
4. **Multi-Environment**: Different configs per environment (dev/staging/prod)
5. **Version Control**: DB migrations track schema changes over time

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Clients still using old env vars | Update all clients; add deprecation warnings |
| Invalid config breaks service | Validation before save; keep old config in audit for rollback |
| Performance impact from DB queries | Add Redis caching with TTL |
| Migration complexity | Phased rollout; maintain env fallback during transition |

## Future Enhancements

1. **Config Versioning**: Support rolling back to previous versions
2. **Environment-Specific Configs**: Separate configs per deployment environment
3. **Config Validation Webhook**: Notify on config changes via webhook
4. **UI Dashboard**: Admin interface for managing service configs
5. **Secret Management**: Integrate with HashiCorp Vault or AWS Secrets Manager for sensitive values

## Next Steps

1. Review this plan and provide feedback
2. Prioritize which services to migrate first
3. Decide on caching strategy (immediate vs. later)
4. Determine authentication requirements for config endpoints
5. Begin implementation once approved
