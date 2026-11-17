"""Comparaison des moteurs : moteur qui a proposé un pari (Coupon intelligent, montante)

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-18 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bets", sa.Column("engine", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("bets", "engine")
