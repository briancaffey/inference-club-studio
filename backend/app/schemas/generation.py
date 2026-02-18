import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GenerationCreate(BaseModel):
    prompt: str
    width: int = Field(default=1024, ge=64, le=2048)
    height: int = Field(default=1024, ge=64, le=2048)
    num_steps: int = Field(default=16, ge=1, le=100)
    cfg_scale: float = Field(default=1.0, ge=0.0, le=30.0)
    seed: int = Field(default=-1, ge=-1)


class GenerationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cut_id: uuid.UUID
    prompt: str
    width: int
    height: int
    num_steps: int
    cfg_scale: float
    seed: int
    invokeai_reference_image_name: str | None = None
    invokeai_generated_image_name: str | None = None
    actual_seed: int | None = None
    reference_frame_path: str | None = None
    output_image_path: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
