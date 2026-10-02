"""Coupons du jour (Coupon intelligent)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-02 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "smart_coupons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("profile", sa.String(length=16), nullable=False),
        sa.Column("size", sa.SmallInteger(), nullable=False),
        sa.Column("selections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_odds", sa.Numeric(10, 2), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", "profile"),
    )
    op.create_index("ix_smart_coupons_day", "smart_coupons", ["day"])


def downgrade() -> None:
    op.drop_index("ix_smart_coupons_day", table_name="smart_coupons")
    op.drop_table("smart_coupons")
