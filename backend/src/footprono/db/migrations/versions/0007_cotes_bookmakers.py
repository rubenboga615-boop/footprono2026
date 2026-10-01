"""Cotes des bookmakers pour les matchs à venir (API-Football)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30 08:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bookmaker_odds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bookmaker", sa.String(length=32), nullable=False),
        sa.Column("bet", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column("price", sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_bookmaker_odds_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_file_id"], ["raw_files.id"], name=op.f("fk_bookmaker_odds_raw_file_id_raw_files")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookmaker_odds")),
    )
    op.create_index(op.f("ix_bookmaker_odds_match_id"), "bookmaker_odds", ["match_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bookmaker_odds_match_id"), table_name="bookmaker_odds")
    op.drop_table("bookmaker_odds")
