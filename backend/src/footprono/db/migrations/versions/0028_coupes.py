"""Coupes d'Europe : tour du match et terrain neutre (finales)

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-05 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("round", sa.String(length=60), nullable=True))
    op.add_column(
        "matches",
        sa.Column("neutral", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("matches", "neutral")
    op.drop_column("matches", "round")
