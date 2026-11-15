"""Comparaison des moteurs (K6) : propositions des deux moteurs, chances avant les matchs

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-15 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engine_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engine", sa.SmallInteger(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("key", sa.String(400), nullable=False),
        sa.Column("selections", postgresql.JSONB(), nullable=False),
        sa.Column("total_odds", sa.Numeric(10, 2), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("payout", sa.Integer(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("engine", "source", "key"),
    )
    op.create_index("ix_engine_proposals_status", "engine_proposals", ["status"])
    op.create_table(
        "engine_match_chances",
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("engine1", postgresql.JSONB(), nullable=False),
        sa.Column("engine2", postgresql.JSONB(), nullable=False),
        sa.Column("calibrated", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("engine_match_chances")
    op.drop_index("ix_engine_proposals_status", "engine_proposals")
    op.drop_table("engine_proposals")
