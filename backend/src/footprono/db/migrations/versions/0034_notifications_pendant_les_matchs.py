"""Notifications pendant les matchs d'un coupon : état « pour l'instant » de chaque sélection
et réglage du joueur (tout, validé-perdu seulement, rien)

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-12 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bet_selections", sa.Column("live_state", sa.String(10), nullable=True))
    op.add_column(
        "users",
        sa.Column("match_notifications", sa.String(8), server_default="all", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "match_notifications")
    op.drop_column("bet_selections", "live_state")
