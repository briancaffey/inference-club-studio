"""add studio voice tracking fields

Revision ID: 9f3c9a7e4d1b
Revises: d4f1f76b8d2a
Create Date: 2026-02-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9f3c9a7e4d1b"
down_revision: Union[str, Sequence[str], None] = "d4f1f76b8d2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "narration_segments",
        sa.Column("studio_voice_audio_path", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "narration_segments",
        sa.Column(
            "studio_voice_status",
            sa.String(length=50),
            nullable=False,
            server_default="not_cleaned",
        ),
    )
    op.add_column(
        "narration_segments",
        sa.Column("studio_voice_error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "narration_segments",
        sa.Column("studio_voice_cleaned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("narration_segments", "studio_voice_status", server_default=None)

    op.add_column(
        "narration_variants",
        sa.Column("studio_voice_audio_path", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "narration_variants",
        sa.Column(
            "studio_voice_status",
            sa.String(length=50),
            nullable=False,
            server_default="not_cleaned",
        ),
    )
    op.add_column(
        "narration_variants",
        sa.Column("studio_voice_error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "narration_variants",
        sa.Column("studio_voice_cleaned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("narration_variants", "studio_voice_status", server_default=None)


def downgrade() -> None:
    op.drop_column("narration_variants", "studio_voice_cleaned_at")
    op.drop_column("narration_variants", "studio_voice_error_message")
    op.drop_column("narration_variants", "studio_voice_status")
    op.drop_column("narration_variants", "studio_voice_audio_path")

    op.drop_column("narration_segments", "studio_voice_cleaned_at")
    op.drop_column("narration_segments", "studio_voice_error_message")
    op.drop_column("narration_segments", "studio_voice_status")
    op.drop_column("narration_segments", "studio_voice_audio_path")
