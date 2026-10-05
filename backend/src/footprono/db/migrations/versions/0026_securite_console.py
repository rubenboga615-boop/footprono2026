"""Sécurité de la console : code à 6 chiffres, révocation des jetons, journal des actions

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-05 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(length=255), nullable=True))
    op.add_column(
        "users", sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["users.id"], name=op.f("fk_admin_actions_admin_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_actions")),
    )  # fmt: skip
    op.create_index(op.f("ix_admin_actions_admin_id"), "admin_actions", ["admin_id"])
    op.create_index(op.f("ix_admin_actions_created_at"), "admin_actions", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_actions_created_at"), table_name="admin_actions")
    op.drop_index(op.f("ix_admin_actions_admin_id"), table_name="admin_actions")
    op.drop_table("admin_actions")
    op.drop_column("users", "tokens_valid_after")
    op.drop_column("users", "totp_secret")
