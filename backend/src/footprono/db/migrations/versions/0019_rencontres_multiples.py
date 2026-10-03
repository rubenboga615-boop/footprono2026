"""Plusieurs rencontres d'une même affiche dans une saison (seconde phase, trois tours)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-03 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "matches", sa.Column("leg", sa.SmallInteger(), server_default="1", nullable=False)
    )
    op.drop_constraint("uq_matches_season_id", "matches", type_="unique")
    op.create_unique_constraint(
        "uq_matches_season_id", "matches", ["season_id", "home_team_id", "away_team_id", "leg"]
    )
    op.create_check_constraint("ck_matches_leg_positive", "matches", "leg >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_matches_leg_positive", "matches", type_="check")
    op.execute("DELETE FROM matches WHERE leg > 1")
    op.drop_constraint("uq_matches_season_id", "matches", type_="unique")
    op.create_unique_constraint(
        "uq_matches_season_id", "matches", ["season_id", "home_team_id", "away_team_id"]
    )
    op.drop_column("matches", "leg")
