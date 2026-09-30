"""Suivi en direct et origine du score final

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-30 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("live_minute", sa.SmallInteger()),
    ("live_home_goals", sa.SmallInteger()),
    ("live_away_goals", sa.SmallInteger()),
    ("live_updated_at", sa.DateTime(timezone=True)),
    ("result_source", sa.String(length=16)),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column("matches", sa.Column(name, type_, nullable=True))
    # Scores déjà en base : venus de football-data (ou d'Understat pour la saison
    # en cours, avant sa publication) ; on les considère confirmés.
    op.execute("UPDATE matches SET result_source = 'football_data' WHERE status = 'finished'")


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("matches", name)
