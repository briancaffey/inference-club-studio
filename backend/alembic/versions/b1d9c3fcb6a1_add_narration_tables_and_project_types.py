"""add narration tables and project types

Revision ID: b1d9c3fcb6a1
Revises: 6e5f4d1a9c10
Create Date: 2026-02-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1d9c3fcb6a1"
down_revision: Union[str, Sequence[str], None] = "6e5f4d1a9c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "projects",
        sa.Column(
            "project_type",
            sa.String(length=50),
            nullable=False,
            server_default="video_to_video",
        ),
    )
    op.alter_column("projects", "project_type", server_default=None)

    op.create_table(
        "narration_voice_samples",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("audio_path", sa.String(length=1000), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "narration_segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sanitized_text", sa.Text(), nullable=False),
        sa.Column("service", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("audio_path", sa.String(length=1000), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("selected_variant_id", sa.Integer(), nullable=True),
        sa.Column("voice_sample_id", sa.Integer(), nullable=True),
        sa.Column("magpie_voice", sa.String(length=255), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["voice_sample_id"],
            ["narration_voice_samples.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_narration_segments_project_position",
        "narration_segments",
        ["project_id", "position"],
        unique=False,
    )

    op.create_table(
        "narration_variants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sanitized_text", sa.Text(), nullable=False),
        sa.Column("service", sa.String(length=50), nullable=False),
        sa.Column("audio_path", sa.String(length=1000), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["narration_segments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_narration_variants_segment_id",
        "narration_variants",
        ["segment_id"],
        unique=False,
    )

    op.create_table(
        "narration_transcriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "words_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["narration_segments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("segment_id"),
    )
    op.create_index(
        "ix_narration_transcriptions_segment_id",
        "narration_transcriptions",
        ["segment_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_narration_transcriptions_segment_id",
        table_name="narration_transcriptions",
    )
    op.drop_table("narration_transcriptions")
    op.drop_index("ix_narration_variants_segment_id", table_name="narration_variants")
    op.drop_table("narration_variants")
    op.drop_index(
        "ix_narration_segments_project_position",
        table_name="narration_segments",
    )
    op.drop_table("narration_segments")
    op.drop_table("narration_voice_samples")
    op.drop_column("projects", "project_type")
