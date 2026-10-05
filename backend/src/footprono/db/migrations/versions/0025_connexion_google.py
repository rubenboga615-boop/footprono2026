"""Connexion avec Google : compte Google lié, numéro facultatif

Un compte créé avec Google n'a ni numéro ni mot de passe (``password_hash`` vide) ;
le numéro est demandé seulement au paiement Mobile Money.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-05 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.String(length=16), nullable=True)
    op.add_column("users", sa.Column("google_sub", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.create_unique_constraint(op.f("uq_users_google_sub"), "users", ["google_sub"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_users_google_sub"), "users", type_="unique")
    op.drop_column("users", "email")
    op.drop_column("users", "google_sub")
    op.alter_column("users", "phone", existing_type=sa.String(length=16), nullable=False)
