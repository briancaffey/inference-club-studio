import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    order: int
    original_filename: str
    file_path: str
    file_size: int | None = None
    duration: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None
    codec: str | None = None
    audio_codec: str | None = None
    thumbnail_path: str | None = None
    audio_path: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class CutReorderRequest(BaseModel):
    cut_ids: list[uuid.UUID]


class CutUploadResponse(BaseModel):
    uploaded: list[CutRead]
