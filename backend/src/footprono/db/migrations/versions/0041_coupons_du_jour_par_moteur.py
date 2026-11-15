"""Comparaison des moteurs : coupons du jour du moteur 2 (colonne engine)

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-15 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "smart_coupons",
        sa.Column("engine", sa.SmallInteger(), server_default="1", nullable=False),
    )
    # Nom donné par la convention de nommage (db/base.py) : uq_<table>_<première colonne>.
    op.drop_constraint("uq_smart_coupons_day", "smart_coupons", type_="unique")
    op.create_unique_constraint(
        "uq_smart_coupons_day", "smart_coupons", ["day", "profile", "engine"]
    )


def downgrade() -> None:
    op.execute("DELETE FROM smart_coupons WHERE engine <> 1")
    op.drop_constraint("uq_smart_coupons_day", "smart_coupons", type_="unique")
    op.create_unique_constraint("uq_smart_coupons_day", "smart_coupons", ["day", "profile"])
    op.drop_column("smart_coupons", "engine")
