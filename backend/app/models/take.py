import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TakeStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADING_ASSETS = "uploading_assets"
    GENERATING = "generating"
    DOWNLOADING = "downloading"
    ENCODING_CANNY = "encoding_canny"
    COMPLETED = "completed"
    ERROR = "error"


class Take(Base):
    __tablename__ = "takes"
    __table_args__ = (Index("ix_takes_generation_id", "generation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("generations.id", ondelete="CASCADE")
    )

    # User inputs
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=641)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=449)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False, default=121)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=-1)

    # ComfyUI tracking
    comfyui_prompt_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actual_seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Local file paths
    output_video_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    canny_video_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=TakeStatus.PENDING.value
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

    generation: Mapped["Generation"] = relationship(  # noqa: F821
        back_populates="takes"
    )
