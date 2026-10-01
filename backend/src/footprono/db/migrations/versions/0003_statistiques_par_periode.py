"""Statistiques par équipe et par période (API-Football) ; identifiant API-Football des matchs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29 21:38:20.632749
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_team_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("source", postgresql.ENUM(name="data_source", create_type=False), nullable=False),
        sa.Column(
            "period",
            sa.Enum("full", "first_half", "second_half", name="stat_period"),
            nullable=False,
        ),
        sa.Column("shots_on_goal", sa.SmallInteger(), nullable=True),
        sa.Column("shots_off_goal", sa.SmallInteger(), nullable=True),
        sa.Column("total_shots", sa.SmallInteger(), nullable=True),
        sa.Column("blocked_shots", sa.SmallInteger(), nullable=True),
        sa.Column("shots_inside_box", sa.SmallInteger(), nullable=True),
        sa.Column("shots_outside_box", sa.SmallInteger(), nullable=True),
        sa.Column("fouls", sa.SmallInteger(), nullable=True),
        sa.Column("corners", sa.SmallInteger(), nullable=True),
        sa.Column("offsides", sa.SmallInteger(), nullable=True),
        sa.Column("possession", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("yellow_cards", sa.SmallInteger(), nullable=True),
        sa.Column("red_cards", sa.SmallInteger(), nullable=True),
        sa.Column("goalkeeper_saves", sa.SmallInteger(), nullable=True),
        sa.Column("total_passes", sa.SmallInteger(), nullable=True),
        sa.Column("passes_accurate", sa.SmallInteger(), nullable=True),
        sa.Column("passes_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("expected_goals", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("goals_prevented", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("raw_file_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_match_team_stats_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_file_id"],
            ["raw_files.id"],
            name=op.f("fk_match_team_stats_raw_file_id_raw_files"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_match_team_stats_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_team_stats")),
        sa.UniqueConstraint(
            "match_id", "team_id", "source", "period", name=op.f("uq_match_team_stats_match_id")
        ),
    )
    op.create_index(
        op.f("ix_match_team_stats_match_id"), "match_team_stats", ["match_id"], unique=False
    )
    op.add_column("matches", sa.Column("api_football_id", sa.Integer(), nullable=True))
    op.create_unique_constraint(op.f("uq_matches_api_football_id"), "matches", ["api_football_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_matches_api_football_id"), "matches", type_="unique")
    op.drop_column("matches", "api_football_id")
    op.drop_index(op.f("ix_match_team_stats_match_id"), table_name="match_team_stats")
    op.drop_table("match_team_stats")
    sa.Enum(name="stat_period").drop(op.get_bind(), checkfirst=True)
