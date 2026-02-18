import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _snap_dim(v: int) -> int:
    """Snap a dimension to the nearest valid LTX value (32n + 1)."""
    n = round((v - 1) / 32)
    n = max(n, 2)  # minimum 65
    return 32 * n + 1


def _snap_frames(v: int) -> int:
    """Snap frame count to the nearest valid LTX value (8n + 1)."""
    n = round((v - 1) / 8)
    n = max(n, 1)  # minimum 9
    return 8 * n + 1


class TakeCreate(BaseModel):
    prompt: str
    width: int = Field(default=641, ge=65, le=1281)
    height: int = Field(default=449, ge=65, le=1281)
    frame_count: int = Field(default=121, ge=9, le=257)
    seed: int = Field(default=-1, ge=-1)

    @model_validator(mode="after")
    def snap_to_valid_ltx_params(self) -> "TakeCreate":
        self.width = _snap_dim(self.width)
        self.height = _snap_dim(self.height)
        self.frame_count = _snap_frames(self.frame_count)
        return self


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
