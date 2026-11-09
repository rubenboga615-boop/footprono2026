"""Données du direct : événements, relevés, compositions, statistiques des joueurs

Plan du 10/11/2026, étape 1 : tirées de ``/fixtures?ids=`` (déjà demandé toutes les
2 minutes pendant les matchs).

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-10 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _match() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "match_id", sa.Integer(), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        _match(),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("minute", sa.SmallInteger()),
        sa.Column("extra", sa.SmallInteger()),
        sa.Column("side", sa.String(4)),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(64)),
        sa.Column("player_api_id", sa.Integer()),
        sa.Column("player", sa.String(96)),
        sa.Column("assist_api_id", sa.Integer()),
        sa.Column("assist", sa.String(96)),
        sa.Column("comments", sa.String(160)),
    )
    op.create_index("ix_match_events_match_id", "match_events", ["match_id"])
    op.create_table(
        "live_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        _match(),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("minute", sa.SmallInteger(), nullable=False),
        sa.Column("extra", sa.SmallInteger(), nullable=False),
        sa.Column("home_goals", sa.SmallInteger()),
        sa.Column("away_goals", sa.SmallInteger()),
        sa.Column("home_stats", postgresql.JSONB()),
        sa.Column("away_stats", postgresql.JSONB()),
        sa.Column("raw_file_id", sa.Integer(), sa.ForeignKey("raw_files.id")),
        sa.UniqueConstraint("match_id", "status", "minute", "extra"),
    )
    op.create_index("ix_live_snapshots_match_id", "live_snapshots", ["match_id"])
    op.create_table(
        "match_lineups",
        sa.Column("id", sa.Integer(), primary_key=True),
        _match(),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("formation", sa.String(16)),
        sa.Column("coach_api_id", sa.Integer()),
        sa.Column("coach", sa.String(96)),
        sa.UniqueConstraint("match_id", "side"),
    )
    op.create_index("ix_match_lineups_match_id", "match_lineups", ["match_id"])
    op.create_table(
        "match_lineup_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        _match(),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("starter", sa.Boolean(), nullable=False),
        sa.Column("player_api_id", sa.Integer()),
        sa.Column("name", sa.String(96), nullable=False),
        sa.Column("number", sa.SmallInteger()),
        sa.Column("position", sa.String(4)),
        sa.Column("grid", sa.String(8)),
    )
    op.create_index("ix_match_lineup_players_match_id", "match_lineup_players", ["match_id"])
    op.create_index(
        "ix_match_lineup_players_player_api_id", "match_lineup_players", ["player_api_id"]
    )
    op.create_table(
        "player_match_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        _match(),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("player_api_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(96), nullable=False),
        sa.Column("minutes", sa.SmallInteger()),
        sa.Column("rating", sa.Numeric(4, 2)),
        sa.Column("goals", sa.SmallInteger()),
        sa.Column("assists", sa.SmallInteger()),
        sa.Column("shots", sa.SmallInteger()),
        sa.Column("shots_on", sa.SmallInteger()),
        sa.Column("yellow", sa.SmallInteger()),
        sa.Column("red", sa.SmallInteger()),
        sa.Column("stats", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("match_id", "player_api_id"),
    )
    op.create_index("ix_player_match_stats_match_id", "player_match_stats", ["match_id"])
    op.create_index("ix_player_match_stats_player_api_id", "player_match_stats", ["player_api_id"])


def downgrade() -> None:
    for table in (
        "player_match_stats",
        "match_lineup_players",
        "match_lineups",
        "live_snapshots",
        "match_events",
    ):
        op.drop_table(table)
