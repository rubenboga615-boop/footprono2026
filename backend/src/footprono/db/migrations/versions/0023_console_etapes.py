"""Console d'administration : étape en cours d'une tâche (suivi en direct)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-05 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("admin_jobs", sa.Column("step", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("admin_jobs", "step")
