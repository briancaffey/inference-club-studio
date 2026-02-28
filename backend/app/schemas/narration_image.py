import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NarrationImageFrameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    series_id: uuid.UUID
    parent_frame_id: uuid.UUID | None = None
    step_key: str | None = None
    step_order: int
    is_fork: bool
    prompt: str
    mode: str
    status: str
    width: int
    height: int
    num_steps: int
    cfg_scale: float
    seed: int
    invokeai_reference_image_name: str | None = None
    invokeai_generated_image_name: str | None = None
    actual_seed: int | None = None
    output_image_path: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class NarrationImageSeriesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    segment_id: int
    name: str | None = None
    source_prompt: str | None = None
    plan_json: dict | None = None
    status: str
    error_message: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    frames: list[NarrationImageFrameRead]


class NarrationImageSeriesCreate(BaseModel):
    name: str | None = None
    initial_prompt: str | None = None
    width: int = Field(default=1360, ge=64, le=2048)
    height: int = Field(default=768, ge=64, le=2048)
    num_steps: int = Field(default=16, ge=1, le=100)
    cfg_scale: float = Field(default=1.0, ge=0.0, le=30.0)
    seed: int = Field(default=-1, ge=-1)
    auto_generate: bool = False


class NarrationImageSeriesAutoCreate(BaseModel):
    creative_direction: str = Field(min_length=1)
    name: str | None = None
    target_images: int = Field(default=4, ge=2, le=12)
    width: int = Field(default=1360, ge=64, le=2048)
    height: int = Field(default=768, ge=64, le=2048)
    num_steps: int = Field(default=16, ge=1, le=100)
    cfg_scale: float = Field(default=1.0, ge=0.0, le=30.0)
    seed: int = Field(default=-1, ge=-1)


class NarrationImageFrameCreate(BaseModel):
    prompt: str = Field(min_length=1)
    parent_frame_id: uuid.UUID | None = None
    mode: Literal["text_to_image", "image_to_image"] | None = None
    is_fork: bool = False
    width: int = Field(default=1360, ge=64, le=2048)
    height: int = Field(default=768, ge=64, le=2048)
    num_steps: int = Field(default=16, ge=1, le=100)
    cfg_scale: float = Field(default=1.0, ge=0.0, le=30.0)
    seed: int = Field(default=-1, ge=-1)


class NarrationImageRegenerateRequest(BaseModel):
    include_descendants: bool = True
    auto_generate: bool = True


class NarrationImagePromptSuggestionRequest(BaseModel):
    source_frame_id: uuid.UUID | None = None
    guidance: str | None = None
    count: int = Field(default=3, ge=1, le=8)


class NarrationImagePromptSuggestionResponse(BaseModel):
    suggestions: list[str]
