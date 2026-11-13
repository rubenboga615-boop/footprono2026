"""Coupon en direct : propositions enregistrées pour la Fiabilité (maquette D15)

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-13 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "live_coupon_picks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile", sa.String(16), nullable=False),
        sa.Column("moment", sa.String(16), nullable=False),
        sa.Column("minute", sa.SmallInteger(), nullable=True),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("line", sa.String(16), nullable=False),
        sa.Column("selection", sa.String(32), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("odds", sa.Numeric(10, 3), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.String(10), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("match_id", "profile", "moment"),
    )
    op.create_index("ix_live_coupon_picks_match_id", "live_coupon_picks", ["match_id"])
    op.create_index("ix_live_coupon_picks_result", "live_coupon_picks", ["result"])


def downgrade() -> None:
    op.drop_table("live_coupon_picks")
