"""add narration segment final and recent-generation fields

Revision ID: c2d8e8df4f14
Revises: 9f3c9a7e4d1b
Create Date: 2026-02-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d8e8df4f14"
down_revision: Union[str, Sequence[str], None] = "9f3c9a7e4d1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "narration_segments",
        sa.Column(
            "is_final",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column("narration_segments", "is_final", server_default=None)
    op.add_column(
        "narration_segments",
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("narration_segments", "last_generated_at")
    op.drop_column("narration_segments", "is_final")
