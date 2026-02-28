import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NarrationImageSeriesStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    GENERATING = "generating"
    COMPLETED = "completed"
    ERROR = "error"


class NarrationImageFrameStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    ERROR = "error"


class NarrationImageGenerationMode(str, enum.Enum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"


class NarrationImageSeries(Base):
    __tablename__ = "narration_image_series"
    __table_args__ = (
        Index(
            "ix_narration_image_series_segment_id_created_at",
            "segment_id",
            "created_at",
        ),
        Index("ix_narration_image_series_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    segment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("narration_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=NarrationImageSeriesStatus.DRAFT.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    segment: Mapped["NarrationSegment"] = relationship(  # noqa: F821
        back_populates="image_series"
    )
    frames: Mapped[list["NarrationImageFrame"]] = relationship(
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="NarrationImageFrame.step_order.asc()",
    )


class NarrationImageFrame(Base):
    __tablename__ = "narration_image_frames"
    __table_args__ = (
        Index(
            "ix_narration_image_frames_series_id_step_order",
            "series_id",
            "step_order",
        ),
        Index("ix_narration_image_frames_parent_frame_id", "parent_frame_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("narration_image_series.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_frame_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("narration_image_frames.id", ondelete="SET NULL"),
        nullable=True,
    )
    step_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_fork: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=NarrationImageGenerationMode.TEXT_TO_IMAGE.value,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=NarrationImageFrameStatus.PENDING.value,
    )
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1360)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=768)
    num_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    cfg_scale: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=-1)
    invokeai_reference_image_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    invokeai_generated_image_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    actual_seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_image_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    series: Mapped["NarrationImageSeries"] = relationship(back_populates="frames")
    parent_frame: Mapped["NarrationImageFrame | None"] = relationship(
        "NarrationImageFrame",
        remote_side=[id],
        back_populates="child_frames",
    )
    child_frames: Mapped[list["NarrationImageFrame"]] = relationship(
        "NarrationImageFrame",
        back_populates="parent_frame",
        cascade="all",
    )
