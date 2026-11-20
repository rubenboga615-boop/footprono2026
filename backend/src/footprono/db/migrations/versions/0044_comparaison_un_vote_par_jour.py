"""Comparaison des moteurs : une proposition par joueur, par moteur et par jour

Audit du 20/11/2026 (point B) : un seul joueur pouvait enregistrer des centaines de
propositions et décider du verdict moteur 1 / moteur 2.

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "engine_proposals",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.add_column("engine_proposals", sa.Column("day", sa.Date(), nullable=True))
    op.execute("UPDATE engine_proposals SET day = (proposed_at AT TIME ZONE 'UTC')::date")
    op.create_index(
        "uq_engine_proposals_user_day",
        "engine_proposals",
        ["engine", "source", "user_id", "day"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_engine_proposals_user_day", table_name="engine_proposals")
    op.drop_column("engine_proposals", "day")
    op.drop_column("engine_proposals", "user_id")
