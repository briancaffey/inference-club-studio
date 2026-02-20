import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class NarrationSegment(Base):
    __tablename__ = "narration_segments"
    __table_args__ = (
        Index(
            "ix_narration_segments_project_position",
            "project_id",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sanitized_text: Mapped[str] = mapped_column(Text, nullable=False)
    service: Mapped[str] = mapped_column(String(50), nullable=False, default="dia")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    audio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generation_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    selected_variant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voice_sample_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("narration_voice_samples.id", ondelete="SET NULL"),
        nullable=True,
    )
    magpie_voice: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project: Mapped["Project"] = relationship(back_populates="narration_segments")
    variants: Mapped[list["NarrationVariant"]] = relationship(
        back_populates="segment",
        cascade="all, delete-orphan",
        order_by="NarrationVariant.created_at.desc()",
    )
    transcription: Mapped["NarrationTranscription | None"] = relationship(
        back_populates="segment",
        cascade="all, delete-orphan",
        uselist=False,
    )
    voice_sample: Mapped["NarrationVoiceSample | None"] = relationship(
        back_populates="segments",
    )


class NarrationVariant(Base):
    __tablename__ = "narration_variants"
    __table_args__ = (Index("ix_narration_variants_segment_id", "segment_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("narration_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sanitized_text: Mapped[str] = mapped_column(Text, nullable=False)
    service: Mapped[str] = mapped_column(String(50), nullable=False)
    audio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    segment: Mapped["NarrationSegment"] = relationship(back_populates="variants")


class NarrationVoiceSample(Base):
    __tablename__ = "narration_voice_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    segments: Mapped[list[NarrationSegment]] = relationship(
        back_populates="voice_sample",
    )


class NarrationTranscription(Base):
    __tablename__ = "narration_transcriptions"
    __table_args__ = (Index("ix_narration_transcriptions_segment_id", "segment_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("narration_segments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    words_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    segment: Mapped["NarrationSegment"] = relationship(back_populates="transcription")
