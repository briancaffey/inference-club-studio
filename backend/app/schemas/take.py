import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TakeCreate(BaseModel):
    prompt: str
    width: int = Field(default=640, ge=64, le=1280)
    height: int = Field(default=448, ge=64, le=1280)
    frame_count: int = Field(default=122, ge=1, le=257)
    seed: int = Field(default=-1, ge=-1)


class TakeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    generation_id: uuid.UUID
    prompt: str
    width: int
    height: int
    frame_count: int
    seed: int
    comfyui_prompt_id: str | None = None
    actual_seed: int | None = None
    output_video_path: str | None = None
    canny_video_path: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
