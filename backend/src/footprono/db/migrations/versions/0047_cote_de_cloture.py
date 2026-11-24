"""Cote de clôture et mesure en silence (plan qualité du 24/11/2026, étape 2)

Pour chaque sélection proposée ou jouée : la dernière cote relevée avant le coup d'envoi
(« clôture »), seul juge qui dit si l'on bat le bookmaker. Les « occasions » (moteur au-dessus
de la cote), cachées aux joueurs, sont enregistrées ici pour être mesurées.

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-24 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("bet_selections", "odds_alert_hits"):
        op.add_column(table, sa.Column("closing_odds", sa.Numeric(8, 3), nullable=True))
        op.add_column(
            table, sa.Column("closing_checked_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.add_column("odds_alert_hits", sa.Column("result", sa.String(10), nullable=True))
    op.create_table(
        "silent_picks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("competition", sa.String(16), nullable=False),
        sa.Column("market", sa.String(40), nullable=False),
        sa.Column("line", sa.String(10), nullable=False, server_default=""),
        sa.Column("selection", sa.String(40), nullable=False),
        sa.Column("bookmaker", sa.String(40), nullable=False),
        sa.Column("odds", sa.Numeric(8, 3), nullable=False),
        sa.Column("engine", sa.Float(), nullable=False),
        sa.Column("closing_odds", sa.Numeric(8, 3), nullable=True),
        sa.Column("closing_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(10), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source", "match_id", "market", "line", "selection"),
    )


def downgrade() -> None:
    op.drop_table("silent_picks")
    op.drop_column("odds_alert_hits", "result")
    for table in ("bet_selections", "odds_alert_hits"):
        op.drop_column(table, "closing_checked_at")
        op.drop_column(table, "closing_odds")
