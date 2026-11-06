"""Mode bêta : partage anonyme volontaire des testeurs (FP_BETA_SHARING)

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-07 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("beta_sharing", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("beta_number", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_users_beta_number", "users", ["beta_number"])
    op.create_table(
        "beta_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("beta_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=128), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=200), nullable=True),
    )
    op.create_index("ix_beta_events_beta_number", "beta_events", ["beta_number"])


def downgrade() -> None:
    op.drop_index("ix_beta_events_beta_number", "beta_events")
    op.drop_table("beta_events")
    op.drop_constraint("uq_users_beta_number", "users", type_="unique")
    op.drop_column("users", "beta_number")
    op.drop_column("users", "beta_sharing")
