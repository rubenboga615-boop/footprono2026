"""Matchs en direct : minutes de temps additionnel (``fixture.status.extra``)

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-07 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("live_extra", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "live_extra")
