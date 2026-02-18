import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    metadata: dict | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    metadata: dict | None = None


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    cut_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProjectDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    metadata: dict | None = None
    cuts: list["CutRead"] = []
    created_at: datetime
    updated_at: datetime


from app.schemas.cut import CutRead  # noqa: E402

ProjectDetail.model_rebuild()
