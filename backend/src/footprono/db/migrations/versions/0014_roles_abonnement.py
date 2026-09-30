"""Rôles et abonnement Premium

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-30 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("role", sa.String(length=8), server_default="user", nullable=False)
    )
    op.add_column("users", sa.Column("premium_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "subscription_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("premium_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_subscription_events_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_events")),
    )
    op.create_index(op.f("ix_subscription_events_user_id"), "subscription_events", ["user_id"])


def downgrade() -> None:
    op.drop_table("subscription_events")
    op.drop_column("users", "premium_until")
    op.drop_column("users", "role")
