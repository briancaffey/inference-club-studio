"""add narration image sequence tables

Revision ID: f7c1b2e4a8d9
Revises: c2d8e8df4f14
Create Date: 2026-02-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f7c1b2e4a8d9"
down_revision: Union[str, Sequence[str], None] = "c2d8e8df4f14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "narration_image_series",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("source_prompt", sa.Text(), nullable=True),
        sa.Column(
            "plan_json",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["narration_segments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_narration_image_series_segment_id_created_at",
        "narration_image_series",
        ["segment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_narration_image_series_status",
        "narration_image_series",
        ["status"],
        unique=False,
    )

    op.create_table(
        "narration_image_frames",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("series_id", sa.UUID(), nullable=False),
        sa.Column("parent_frame_id", sa.UUID(), nullable=True),
        sa.Column("step_key", sa.String(length=120), nullable=True),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("is_fork", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("num_steps", sa.Integer(), nullable=False),
        sa.Column("cfg_scale", sa.Float(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column(
            "invokeai_reference_image_name",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            "invokeai_generated_image_name",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column("actual_seed", sa.BigInteger(), nullable=True),
        sa.Column("output_image_path", sa.String(length=1000), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["narration_image_series.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_frame_id"],
            ["narration_image_frames.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("narration_image_frames", "is_fork", server_default=None)
    op.create_index(
        "ix_narration_image_frames_series_id_step_order",
        "narration_image_frames",
        ["series_id", "step_order"],
        unique=False,
    )
    op.create_index(
        "ix_narration_image_frames_parent_frame_id",
        "narration_image_frames",
        ["parent_frame_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_narration_image_frames_parent_frame_id",
        table_name="narration_image_frames",
    )
    op.drop_index(
        "ix_narration_image_frames_series_id_step_order",
        table_name="narration_image_frames",
    )
    op.drop_table("narration_image_frames")

    op.drop_index(
        "ix_narration_image_series_status",
        table_name="narration_image_series",
    )
    op.drop_index(
        "ix_narration_image_series_segment_id_created_at",
        table_name="narration_image_series",
    )
    op.drop_table("narration_image_series")
