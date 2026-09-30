"""Arbitre selon API-Football

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-30 03:53:00.656480
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("api_referee", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "api_referee")
