"""Montante : palier proposé par le moteur ou composé par le joueur (suivi M2)

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-13 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("montante_steps", sa.Column("suggested", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("montante_steps", "suggested")
