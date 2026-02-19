import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProjectType(str, enum.Enum):
    VIDEO_TO_VIDEO = "video_to_video"
    NARRATION = "narration"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ProjectType.VIDEO_TO_VIDEO.value
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cuts: Mapped[list["Cut"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Cut.order",
    )
    narration_segments: Mapped[list["NarrationSegment"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="NarrationSegment.position",
    )
