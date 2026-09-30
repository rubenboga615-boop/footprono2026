"""Montante

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-30 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "montantes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("start_stake", sa.BigInteger(), nullable=False),
        sa.Column("secure_pct", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("next_stake", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_montantes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_montantes")),
    )
    op.create_index(op.f("ix_montantes_user_id"), "montantes", ["user_id"])
    op.create_table(
        "montante_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("montante_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("odds_min", sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column("odds_max", sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column("bet_id", sa.Integer(), nullable=True),
        sa.Column("out_of_range", sa.Boolean(), nullable=False),
        sa.Column("result", sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(
            ["montante_id"],
            ["montantes.id"],
            name=op.f("fk_montante_steps_montante_id_montantes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bet_id"], ["bets.id"], name=op.f("fk_montante_steps_bet_id_bets")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_montante_steps")),
    )
    op.create_index(op.f("ix_montante_steps_montante_id"), "montante_steps", ["montante_id"])


def downgrade() -> None:
    op.drop_table("montante_steps")
    op.drop_table("montantes")
