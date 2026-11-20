"""Plan de jeu et alertes de cote (maquettes 29 et 30 du nouveau visage, 20/11/2026)

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-20 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "play_plans",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("weekly_budget", sa.Integer(), nullable=True),
        sa.Column("loss_limit", sa.Integer(), nullable=True),
        sa.Column("max_stake", sa.Integer(), nullable=True),
        sa.Column("reminder", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("pause_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending", postgresql.JSONB(), nullable=True),
        sa.Column("pending_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "odds_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "match_id", sa.Integer(), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("market", sa.String(40), nullable=True),
        sa.Column("line", sa.String(10), nullable=True),
        sa.Column("selection", sa.String(40), nullable=True),
        sa.Column("target_odds", sa.Numeric(8, 2), nullable=True),
        sa.Column("start_odds", sa.Numeric(8, 2), nullable=True),
        sa.Column("min_gap", sa.Float(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_odds_alerts_user_id", "odds_alerts", ["user_id"])
    op.create_index("ix_odds_alerts_match_id", "odds_alerts", ["match_id"])
    op.create_table(
        "odds_alert_hits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "alert_id",
            sa.Integer(),
            sa.ForeignKey("odds_alerts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("market", sa.String(40), nullable=False),
        sa.Column("line", sa.String(10), server_default="", nullable=False),
        sa.Column("selection", sa.String(40), nullable=False),
        sa.Column("from_odds", sa.Numeric(8, 2), nullable=True),
        sa.Column("odds", sa.Numeric(8, 2), nullable=False),
        sa.Column("bookmaker", sa.String(40), nullable=False),
        sa.Column("engine", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("alert_id", "match_id"),
    )
    op.create_index("ix_odds_alert_hits_alert_id", "odds_alert_hits", ["alert_id"])
    op.create_index("ix_odds_alert_hits_user_id", "odds_alert_hits", ["user_id"])


def downgrade() -> None:
    op.drop_table("odds_alert_hits")
    op.drop_table("odds_alerts")
    op.drop_table("play_plans")
