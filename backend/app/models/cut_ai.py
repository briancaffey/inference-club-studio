import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CutAIAnalysisType(str, enum.Enum):
    CLIP_OVERVIEW = "clip_overview"
    FIRST_FRAME = "first_frame"
    FLUX_STYLE_CONTENT_PROMPT = "flux_style_content_prompt"


class CutAIStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class CutAIRun(Base):
    __tablename__ = "cut_ai_runs"
    __table_args__ = (
        Index("ix_cut_ai_runs_cut_id_created_at", "cut_id", "created_at"),
        Index(
            "ix_cut_ai_runs_cut_id_type_created_at",
            "cut_id",
            "analysis_type",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cut_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cuts.id", ondelete="CASCADE"), nullable=False
    )
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=CutAIStatus.QUEUED.value
    )
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cut: Mapped["Cut"] = relationship(back_populates="ai_runs")  # noqa: F821


class CutAIState(Base):
    __tablename__ = "cut_ai_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cut_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cuts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    clip_overview_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_frame_description_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    first_frame_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    clip_overview_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cut_ai_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    first_frame_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cut_ai_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    clip_overview_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=CutAIStatus.PENDING.value
    )
    first_frame_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=CutAIStatus.PENDING.value
    )
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cut: Mapped["Cut"] = relationship(back_populates="ai_state")  # noqa: F821
    clip_overview_run: Mapped["CutAIRun | None"] = relationship(  # noqa: F821
        "CutAIRun",
        foreign_keys=[clip_overview_run_id],
    )
    first_frame_run: Mapped["CutAIRun | None"] = relationship(  # noqa: F821
        "CutAIRun",
        foreign_keys=[first_frame_run_id],
    )


class PromptDraft(Base):
    __tablename__ = "prompt_drafts"
    __table_args__ = (
        Index("ix_prompt_drafts_cut_id_created_at", "cut_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cut_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cuts.id", ondelete="CASCADE"), nullable=False
    )
    draft_type: Mapped[str] = mapped_column(String(50), nullable=False)
    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cut_ai_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    cut: Mapped["Cut"] = relationship(back_populates="prompt_drafts")  # noqa: F821
    source_run: Mapped["CutAIRun | None"] = relationship("CutAIRun")  # noqa: F821
