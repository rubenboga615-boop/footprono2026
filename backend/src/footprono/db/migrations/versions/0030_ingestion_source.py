"""Journal des ingestions : sources sur 128 caractères

L'ingestion du matin enregistrait « football_data+understat+api_football » (36 caractères,
plus encore avec deux saisons en cours) dans une colonne de 32 : elle échouait chaque
matin avant de commencer (constaté le 06/11/2026 dans la console).

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-06 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "ingestion_runs", "source", type_=sa.String(length=128), existing_type=sa.String(32)
    )


def downgrade() -> None:
    op.alter_column(
        "ingestion_runs",
        "source",
        type_=sa.String(length=32),
        existing_type=sa.String(128),
        postgresql_using="left(source, 32)",
    )
