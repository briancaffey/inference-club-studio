import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CutAIRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cut_id: uuid.UUID
    analysis_type: str
    status: str
    prompt_key: str
    prompt_input: dict | None = None
    prompt_text: str
    response_text: str | None = None
    model_name: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class CutAIStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cut_id: uuid.UUID
    clip_overview_text: str | None = None
    first_frame_description_text: str | None = None
    first_frame_path: str | None = None
    clip_overview_status: str
    first_frame_status: str
    last_error_message: str | None = None
    clip_overview_run: CutAIRunRead | None = None
    first_frame_run: CutAIRunRead | None = None
    created_at: datetime
    updated_at: datetime


class CutAIRegenerateRequest(BaseModel):
    types: list[str] = Field(default_factory=lambda: ["clip_overview", "first_frame"])


class FluxPromptDraftRequest(BaseModel):
    style: str = Field(min_length=1)
    content: str | None = None


class FluxPromptDraftResponse(BaseModel):
    draft_id: uuid.UUID
    run: CutAIRunRead
    prompt_text: str
    created_at: datetime
