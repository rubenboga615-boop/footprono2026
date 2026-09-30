"""Calendrier API-Football : coup d'envoi exact et statut

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-30 07:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("matches", sa.Column("api_status", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "api_status")
    op.drop_column("matches", "kickoff_at")
