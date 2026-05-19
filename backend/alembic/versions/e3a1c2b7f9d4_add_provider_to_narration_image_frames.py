"""add provider column to narration image frames

Revision ID: e3a1c2b7f9d4
Revises: 40e6d0b58ae1
Create Date: 2026-05-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e3a1c2b7f9d4"
down_revision: Union[str, Sequence[str], None] = "40e6d0b58ae1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "narration_image_frames",
        sa.Column("provider", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("narration_image_frames", "provider")
