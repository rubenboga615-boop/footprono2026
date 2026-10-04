"""Console d'administration : tâches lancées depuis le web et leur journal

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-04 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("exclusive", sa.Boolean(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("summary", sa.String(length=400), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stop_requested", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_admin_jobs_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_jobs")),
    )
    op.create_index(op.f("ix_admin_jobs_action"), "admin_jobs", ["action"])
    op.create_index(op.f("ix_admin_jobs_status"), "admin_jobs", ["status"])
    op.create_table(
        "admin_job_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["admin_jobs.id"],
            name=op.f("fk_admin_job_lines_job_id_admin_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_job_lines")),
    )
    op.create_index(op.f("ix_admin_job_lines_job_id"), "admin_job_lines", ["job_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_job_lines_job_id"), table_name="admin_job_lines")
    op.drop_table("admin_job_lines")
    op.drop_index(op.f("ix_admin_jobs_status"), table_name="admin_jobs")
    op.drop_index(op.f("ix_admin_jobs_action"), table_name="admin_jobs")
    op.drop_table("admin_jobs")
