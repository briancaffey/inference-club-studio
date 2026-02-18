import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GenerationStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTING_FRAME = "extracting_frame"
    UPLOADING_REFERENCE = "uploading_reference"
    GENERATING = "generating"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    ERROR = "error"


class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (Index("ix_generations_cut_id", "cut_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cut_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cuts.id", ondelete="CASCADE")
    )

    # User inputs
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    num_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    cfg_scale: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=-1)

    # InvokeAI tracking
    invokeai_reference_image_name: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    invokeai_generated_image_name: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    actual_seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Local file paths
    reference_frame_path: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )
    output_image_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=GenerationStatus.PENDING.value
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cut: Mapped["Cut"] = relationship(back_populates="generations")  # noqa: F821
    takes: Mapped[list["Take"]] = relationship(  # noqa: F821
        back_populates="generation",
        cascade="all, delete-orphan",
        order_by="Take.created_at.desc()",
    )
