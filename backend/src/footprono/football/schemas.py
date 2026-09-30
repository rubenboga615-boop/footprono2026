"""Schémas de réponse de l'API des données sportives.

Les valeurs absentes de la source sont renvoyées à ``null`` : l'API ne
complète jamais une donnée manquante.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from footprono.football.models import DataSource, MatchStatus, OddsTiming, StatPeriod


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SeasonOut(_Out):
    start_year: int
    label: str
    matches: int
    finished: int


class CompetitionOut(_Out):
    code: str
    name: str
    country: str
    n_teams: int
    seasons: list[SeasonOut]


class TeamOut(_Out):
    id: int
    name: str
    country: str


class MatchOut(_Out):
    id: int
    competition: str
    season: int
    match_date: date
    kickoff_time: time | None = Field(
        description="heure publiée par football-data (fuseau à confirmer)"
    )
    kickoff_at: datetime | None = Field(
        default=None, description="coup d'envoi exact (UTC) selon API-Football"
    )
    status: MatchStatus
    api_status: str | None = Field(
        default=None, description="statut API-Football : NS à venir, PST reporté, FT terminé…"
    )
    home_team: TeamOut
    away_team: TeamOut
    home_goals: int | None
    away_goals: int | None


class BookmakerOddsOut(BaseModel):
    """Dernière cote relevée ; ``market`` est vide si le pari n'est pas encore traduit."""

    bookmaker: str
    bet: str
    value: str
    price: Decimal
    market: str | None
    line: str | None
    selection: str | None
    fetched_at: datetime
    source_updated_at: datetime | None


class MatchPage(BaseModel):
    items: list[MatchOut]
    total: int
    limit: int
    offset: int


class MatchStatsOut(_Out):
    home_goals_ht: int | None
    away_goals_ht: int | None
    home_shots: int | None
    away_shots: int | None
    home_shots_on_target: int | None
    away_shots_on_target: int | None
    home_corners: int | None
    away_corners: int | None
    home_fouls: int | None
    away_fouls: int | None
    home_yellow_cards: int | None
    away_yellow_cards: int | None
    home_red_cards: int | None
    away_red_cards: int | None
    referee: str | None
    api_referee: str | None


class AdvancedStatsOut(_Out):
    team_id: int
    source: DataSource
    xg: Decimal | None
    xga: Decimal | None
    npxg: Decimal | None
    npxga: Decimal | None
    ppda_att: int | None
    ppda_def: int | None
    ppda_allowed_att: int | None
    ppda_allowed_def: int | None
    deep: int | None
    deep_allowed: int | None
    xpts: Decimal | None


class OddsOut(_Out):
    source: DataSource
    bookmaker: str
    market: str
    line: Decimal
    timing: OddsTiming
    selection: str
    price: Decimal


class TeamStatsOut(_Out):
    """Statistiques d'une équipe sur une période (match complet ou mi-temps)."""

    team_id: int
    source: DataSource
    period: StatPeriod
    shots_on_goal: int | None
    shots_off_goal: int | None
    total_shots: int | None
    blocked_shots: int | None
    shots_inside_box: int | None
    shots_outside_box: int | None
    fouls: int | None
    corners: int | None
    offsides: int | None
    possession: Decimal | None
    yellow_cards: int | None
    red_cards: int | None
    goalkeeper_saves: int | None
    total_passes: int | None
    passes_accurate: int | None
    passes_pct: Decimal | None
    expected_goals: Decimal | None
    goals_prevented: Decimal | None


class MatchDetailOut(MatchOut):
    api_football_id: int | None
    stats: MatchStatsOut
    advanced_stats: list[AdvancedStatsOut]
    team_stats: list[TeamStatsOut]
    odds: list[OddsOut]
    updated_at: datetime


class IngestionRunOut(_Out):
    id: int
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    parameters: dict[str, Any]


class IngestionRunDetailOut(IngestionRunOut):
    report: dict[str, Any]
