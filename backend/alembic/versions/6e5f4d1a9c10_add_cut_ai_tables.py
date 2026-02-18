"""add cut ai tables

Revision ID: 6e5f4d1a9c10
Revises: a9439f22c9d3
Create Date: 2026-02-18 10:52:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6e5f4d1a9c10"
down_revision: Union[str, Sequence[str], None] = "a9439f22c9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cut_ai_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cut_id", sa.UUID(), nullable=False),
        sa.Column("analysis_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("prompt_key", sa.String(length=100), nullable=False),
        sa.Column(
            "prompt_input",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cut_id"], ["cuts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cut_ai_runs_cut_id_created_at",
        "cut_ai_runs",
        ["cut_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_cut_ai_runs_cut_id_type_created_at",
        "cut_ai_runs",
        ["cut_id", "analysis_type", "created_at"],
        unique=False,
    )

    op.create_table(
        "cut_ai_state",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cut_id", sa.UUID(), nullable=False),
        sa.Column("clip_overview_text", sa.Text(), nullable=True),
        sa.Column("first_frame_description_text", sa.Text(), nullable=True),
        sa.Column("first_frame_path", sa.String(length=1000), nullable=True),
        sa.Column("clip_overview_run_id", sa.UUID(), nullable=True),
        sa.Column("first_frame_run_id", sa.UUID(), nullable=True),
        sa.Column("clip_overview_status", sa.String(length=50), nullable=False),
        sa.Column("first_frame_status", sa.String(length=50), nullable=False),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cut_id"], ["cuts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["clip_overview_run_id"], ["cut_ai_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["first_frame_run_id"], ["cut_ai_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cut_id"),
    )

    op.create_table(
        "prompt_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cut_id", sa.UUID(), nullable=False),
        sa.Column("draft_type", sa.String(length=50), nullable=False),
        sa.Column(
            "input_payload",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("prompt_key", sa.String(length=100), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("source_run_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cut_id"], ["cuts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["cut_ai_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prompt_drafts_cut_id_created_at",
        "prompt_drafts",
        ["cut_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_prompt_drafts_cut_id_created_at", table_name="prompt_drafts")
    op.drop_table("prompt_drafts")
    op.drop_table("cut_ai_state")
    op.drop_index("ix_cut_ai_runs_cut_id_type_created_at", table_name="cut_ai_runs")
    op.drop_index("ix_cut_ai_runs_cut_id_created_at", table_name="cut_ai_runs")
    op.drop_table("cut_ai_runs")
