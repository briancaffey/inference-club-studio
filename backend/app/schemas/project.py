import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.project import ProjectType


class ProjectCreate(BaseModel):
    name: str
    project_type: ProjectType = ProjectType.VIDEO_TO_VIDEO
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
    project_type: ProjectType
    description: str | None = None
    cut_count: int = 0
    segment_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProjectDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    project_type: ProjectType
    description: str | None = None
    metadata: dict | None = None
    segment_count: int = 0
    cuts: list["CutRead"] = []
    created_at: datetime
    updated_at: datetime


from app.schemas.cut import CutRead  # noqa: E402

ProjectDetail.model_rebuild()
