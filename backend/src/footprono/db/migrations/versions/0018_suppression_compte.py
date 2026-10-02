"""Suppression du compte : les paiements restent (comptabilité), sans la personne

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-02 12:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("fk_payments_user_id_users", "payments", type_="foreignkey")
    op.alter_column("payments", "user_id", nullable=True)
    op.create_foreign_key(
        "fk_payments_user_id_users", "payments", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_payments_user_id_users", "payments", type_="foreignkey")
    op.execute("DELETE FROM payments WHERE user_id IS NULL")
    op.alter_column("payments", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_payments_user_id_users", "payments", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
