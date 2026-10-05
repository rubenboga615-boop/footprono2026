"""Notifications de fin de tâche de la console retirées de l'application

Le suivi des tâches reste dans la console ; l'application des joueurs ne
montre plus rien de l'administration.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-05 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'admin_job'")


def downgrade() -> None:
    pass  # notifications effacées : rien à recréer
