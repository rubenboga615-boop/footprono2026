"""Comparaison des moteurs : moteur qui a proposé le pari d'un palier de montante

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-15 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("montante_steps", sa.Column("engine", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("montante_steps", "engine")
