"""Prédictions enregistrées

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-30 06:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prediction_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prediction_runs")),
    )
    op.create_table(
        "match_predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lambda_home", sa.Float(), nullable=False),
        sa.Column("lambda_away", sa.Float(), nullable=False),
        sa.Column("rho", sa.Float(), nullable=False),
        sa.Column("share_home", sa.Float(), nullable=False),
        sa.Column("share_away", sa.Float(), nullable=False),
        sa.Column("markets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_match_predictions_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["prediction_runs.id"],
            name=op.f("fk_match_predictions_run_id_prediction_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_predictions")),
        sa.UniqueConstraint("run_id", "match_id", name=op.f("uq_match_predictions_run_id")),
    )
    op.create_index(
        op.f("ix_match_predictions_match_id"), "match_predictions", ["match_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_match_predictions_match_id"), table_name="match_predictions")
    op.drop_table("match_predictions")
    op.drop_table("prediction_runs")
