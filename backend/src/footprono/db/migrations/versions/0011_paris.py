"""Paris du bookmaker virtuel

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bookmaker_odds", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE bookmaker_odds SET last_seen_at = fetched_at")
    op.alter_column("bookmaker_odds", "last_seen_at", nullable=False)
    op.create_table(
        "bets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("stake", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total_odds", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("potential_payout", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("outcome", sa.String(length=8), nullable=True),
        sa.Column("payout", sa.BigInteger(), nullable=True),
        sa.Column(
            "placed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settlements", sa.Integer(), nullable=False),
        sa.Column("montante_step_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_bets_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bets")),
    )
    op.create_index(op.f("ix_bets_user_id"), "bets", ["user_id"])
    op.create_index(op.f("ix_bets_status"), "bets", ["status"])
    op.create_index(op.f("ix_bets_montante_step_id"), "bets", ["montante_step_id"])
    op.create_table(
        "bet_selections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bet_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=24), nullable=False),
        sa.Column("line", sa.String(length=8), nullable=False),
        sa.Column("selection", sa.String(length=24), nullable=False),
        sa.Column("odds", sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column("bookmaker", sa.String(length=32), nullable=False),
        sa.Column("odds_quote_id", sa.Integer(), nullable=True),
        sa.Column("model_probability", sa.Float(), nullable=True),
        sa.Column("result", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(
            ["bet_id"], ["bets.id"], name=op.f("fk_bet_selections_bet_id_bets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_bet_selections_match_id_matches")
        ),
        sa.ForeignKeyConstraint(
            ["odds_quote_id"],
            ["bookmaker_odds.id"],
            name=op.f("fk_bet_selections_odds_quote_id_bookmaker_odds"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bet_selections")),
    )
    op.create_index(op.f("ix_bet_selections_bet_id"), "bet_selections", ["bet_id"])
    op.create_index(op.f("ix_bet_selections_match_id"), "bet_selections", ["match_id"])


def downgrade() -> None:
    op.drop_table("bet_selections")
    op.drop_table("bets")
    op.drop_column("bookmaker_odds", "last_seen_at")
