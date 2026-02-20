"""add narration quality tracking fields

Revision ID: d4f1f76b8d2a
Revises: b1d9c3fcb6a1
Create Date: 2026-02-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4f1f76b8d2a"
down_revision: Union[str, Sequence[str], None] = "b1d9c3fcb6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "narration_segments",
        sa.Column("quality_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "narration_segments",
        sa.Column(
            "needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "narration_segments",
        sa.Column(
            "generation_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("narration_segments", "needs_review", server_default=None)
    op.alter_column("narration_segments", "generation_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("narration_segments", "generation_attempts")
    op.drop_column("narration_segments", "needs_review")
    op.drop_column("narration_segments", "quality_score")
