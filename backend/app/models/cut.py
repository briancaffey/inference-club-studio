import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CutStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING_METADATA = "processing_metadata"
    EXTRACTING_AUDIO = "extracting_audio"
    READY = "ready"
    ERROR = "error"


class Cut(Base):
    __tablename__ = "cuts"
    __table_args__ = (Index("ix_cuts_project_order", "project_id", "order"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Video metadata (populated by Celery task)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aspect_ratio: Mapped[str | None] = mapped_column(String(20), nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Generated file paths
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=CutStatus.UPLOADED.value
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # For future cut splitting
    parent_cut_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cuts.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project: Mapped["Project"] = relationship(back_populates="cuts")  # noqa: F821
    generations: Mapped[list["Generation"]] = relationship(  # noqa: F821
        back_populates="cut",
        cascade="all, delete-orphan",
    )
    ai_state: Mapped["CutAIState | None"] = relationship(  # noqa: F821
        back_populates="cut",
        cascade="all, delete-orphan",
        uselist=False,
    )
    ai_runs: Mapped[list["CutAIRun"]] = relationship(  # noqa: F821
        back_populates="cut",
        cascade="all, delete-orphan",
        order_by="CutAIRun.created_at.desc()",
    )
    prompt_drafts: Mapped[list["PromptDraft"]] = relationship(  # noqa: F821
        back_populates="cut",
        cascade="all, delete-orphan",
        order_by="PromptDraft.created_at.desc()",
    )
