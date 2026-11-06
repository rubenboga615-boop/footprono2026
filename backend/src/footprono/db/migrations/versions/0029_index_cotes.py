"""Cotes : index par match et bookmaker (Coupon intelligent, suggestions)

Le dernier relevé de chaque cote jouable (1xBet, Bet365) se lisait avec l'index sur le
match seul : la base parcourait aussi les cotes de tous les autres bookmakers (plus de
80 % des lignes) avant de les écarter. Le Coupon intelligent attendait 16 à 19 secondes
en production (essai du 06/11/2026).

Création sans bloquer la collecte des cotes (CONCURRENTLY, hors transaction).

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-06 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_bookmaker_odds_match_bookmaker_bet"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX,
            "bookmaker_odds",
            ["match_id", "bookmaker", "bet", "value", "id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, "bookmaker_odds", postgresql_concurrently=True, if_exists=True)
