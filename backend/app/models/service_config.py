from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class ServiceConfig(Base):
    """Database-backed service configuration with JSONB flexibility."""

    __tablename__ = "service_configs"

    id = Column(Integer, primary_key=True, index=True)
    service_key = Column(String(50), unique=True, nullable=False, index=True)
    config = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    updated_by = Column(String(100), nullable=True)


class ServiceConfigAudit(Base):
    """Audit trail for configuration changes."""

    __tablename__ = "service_config_audits"

    id = Column(Integer, primary_key=True, index=True)
    service_key = Column(String(50), nullable=False, index=True)
    old_config = Column(JSONB, nullable=True)
    new_config = Column(JSONB, nullable=False)
    changed_fields = Column(JSONB, nullable=False)
    updated_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
