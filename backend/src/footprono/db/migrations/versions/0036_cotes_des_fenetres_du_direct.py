"""Coupon en direct : cotes du direct gardées à chaque fenêtre (étude avec les statistiques)

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-13 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "live_window_odds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("moment", sa.String(16), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=True),
        sa.Column("odds", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("match_id", "moment"),
    )
    op.create_index("ix_live_window_odds_match_id", "live_window_odds", ["match_id"])


def downgrade() -> None:
    op.drop_table("live_window_odds")
