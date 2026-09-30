"""Modèles ORM des données sportives.

Principes :
- chaque valeur ingérée garde sa provenance (source, fichier brut, horodatage) ;
- une donnée absente reste ``NULL`` : aucune valeur n'est inventée ;
- les cotes sont stockées telles que publiées par la source, avec leur moment
  de collecte (``pre`` ou ``close``), pour ne jamais confondre une cote
  disponible avant le match avec une cote de clôture.
"""

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class DataSource(StrEnum):
    FOOTBALL_DATA = "football_data"
    UNDERSTAT = "understat"
    API_FOOTBALL = "api_football"


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    FINISHED = "finished"
    # Jamais joué et ne le sera pas (saison arrêtée) : aucun score, exclu des modèles.
    CANCELLED = "cancelled"


class StatPeriod(StrEnum):
    FULL = "full"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"


class OddsTiming(StrEnum):
    PRE = "pre"
    CLOSE = "close"


def _enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(60))
    n_teams: Mapped[int] = mapped_column(SmallInteger)
    football_data_division: Mapped[str | None] = mapped_column(String(8))
    understat_slug: Mapped[str | None] = mapped_column(String(32))
    api_football_id: Mapped[int | None] = mapped_column(Integer)


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("competition_id", "start_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"))
    start_year: Mapped[int] = mapped_column(SmallInteger)

    @property
    def label(self) -> str:
        return f"{self.start_year}-{(self.start_year + 1) % 100:02d}"


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    country: Mapped[str] = mapped_column(String(60))


class TeamAlias(Base):
    """Nom d'une équipe tel qu'écrit par une source donnée."""

    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("source", "alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    source: Mapped[DataSource] = mapped_column(_enum(DataSource, "data_source"))
    alias: Mapped[str] = mapped_column(String(100))


class RawFile(Base):
    """Fichier brut récupéré d'une source, conservé tel quel et identifié par son empreinte."""

    __tablename__ = "raw_files"
    __table_args__ = (UniqueConstraint("source", "sha256"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[DataSource] = mapped_column(_enum(DataSource, "data_source"))
    origin: Mapped[str] = mapped_column(String(500))
    path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        # Dans un championnat, une affiche domicile/extérieur n'a lieu qu'une fois par saison.
        UniqueConstraint("season_id", "home_team_id", "away_team_id"),
        CheckConstraint("home_team_id <> away_team_id", name="distinct_teams"),
        CheckConstraint(
            "(status = 'finished') = (home_goals IS NOT NULL AND away_goals IS NOT NULL)",
            name="finished_has_score",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    match_date: Mapped[date] = mapped_column(Date, index=True)
    # Heure de coup d'envoi telle que publiée par football-data (fuseau à confirmer).
    kickoff_time: Mapped[time | None] = mapped_column(Time)
    status: Mapped[MatchStatus] = mapped_column(_enum(MatchStatus, "match_status"))

    home_goals: Mapped[int | None] = mapped_column(SmallInteger)
    away_goals: Mapped[int | None] = mapped_column(SmallInteger)
    home_goals_ht: Mapped[int | None] = mapped_column(SmallInteger)
    away_goals_ht: Mapped[int | None] = mapped_column(SmallInteger)

    home_shots: Mapped[int | None] = mapped_column(SmallInteger)
    away_shots: Mapped[int | None] = mapped_column(SmallInteger)
    home_shots_on_target: Mapped[int | None] = mapped_column(SmallInteger)
    away_shots_on_target: Mapped[int | None] = mapped_column(SmallInteger)
    home_corners: Mapped[int | None] = mapped_column(SmallInteger)
    away_corners: Mapped[int | None] = mapped_column(SmallInteger)
    home_fouls: Mapped[int | None] = mapped_column(SmallInteger)
    away_fouls: Mapped[int | None] = mapped_column(SmallInteger)
    home_yellow_cards: Mapped[int | None] = mapped_column(SmallInteger)
    away_yellow_cards: Mapped[int | None] = mapped_column(SmallInteger)
    home_red_cards: Mapped[int | None] = mapped_column(SmallInteger)
    away_red_cards: Mapped[int | None] = mapped_column(SmallInteger)
    referee: Mapped[str | None] = mapped_column(String(100))

    football_data_file_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.id"))
    # Identifiant du match chez API-Football (statistiques, temps réel).
    api_football_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    # Arbitre selon API-Football (« Prénom Nom », pays retiré) : disponible pour
    # les 5 championnats, contrairement à ``referee`` (football-data, EPL seulement).
    api_referee: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MatchAdvancedStats(Base):
    """Statistiques avancées d'une équipe dans un match (source : Understat)."""

    __tablename__ = "match_advanced_stats"
    __table_args__ = (UniqueConstraint("match_id", "team_id", "source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    source: Mapped[DataSource] = mapped_column(_enum(DataSource, "data_source"))
    source_match_id: Mapped[str | None] = mapped_column(String(32))
    xg: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    xga: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    npxg: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    npxga: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    ppda_att: Mapped[int | None] = mapped_column(SmallInteger)
    ppda_def: Mapped[int | None] = mapped_column(SmallInteger)
    ppda_allowed_att: Mapped[int | None] = mapped_column(SmallInteger)
    ppda_allowed_def: Mapped[int | None] = mapped_column(SmallInteger)
    deep: Mapped[int | None] = mapped_column(SmallInteger)
    deep_allowed: Mapped[int | None] = mapped_column(SmallInteger)
    xpts: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    raw_file_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.id"))


class MatchTeamStats(Base):
    """Statistiques d'une équipe dans un match, par période (source : API-Football).

    Les compteurs (tirs, corners, cartons…) absents de la réponse valent 0 —
    convention d'API-Football vérifiée contre football-data. Les mesures
    (possession, passes, xG) absentes restent ``NULL``. Les fautes ne sont pas
    fournies par mi-temps : ``NULL`` pour les périodes ``first_half``/``second_half``.
    """

    __tablename__ = "match_team_stats"
    __table_args__ = (UniqueConstraint("match_id", "team_id", "source", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    source: Mapped[DataSource] = mapped_column(_enum(DataSource, "data_source"))
    period: Mapped[StatPeriod] = mapped_column(_enum(StatPeriod, "stat_period"))
    shots_on_goal: Mapped[int | None] = mapped_column(SmallInteger)
    shots_off_goal: Mapped[int | None] = mapped_column(SmallInteger)
    total_shots: Mapped[int | None] = mapped_column(SmallInteger)
    blocked_shots: Mapped[int | None] = mapped_column(SmallInteger)
    shots_inside_box: Mapped[int | None] = mapped_column(SmallInteger)
    shots_outside_box: Mapped[int | None] = mapped_column(SmallInteger)
    fouls: Mapped[int | None] = mapped_column(SmallInteger)
    corners: Mapped[int | None] = mapped_column(SmallInteger)
    offsides: Mapped[int | None] = mapped_column(SmallInteger)
    possession: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    yellow_cards: Mapped[int | None] = mapped_column(SmallInteger)
    red_cards: Mapped[int | None] = mapped_column(SmallInteger)
    goalkeeper_saves: Mapped[int | None] = mapped_column(SmallInteger)
    total_passes: Mapped[int | None] = mapped_column(SmallInteger)
    passes_accurate: Mapped[int | None] = mapped_column(SmallInteger)
    passes_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    expected_goals: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    goals_prevented: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    raw_file_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.id"))


class MatchOdds(Base):
    """Une cote publiée : bookmaker, marché, ligne, moment et sélection."""

    __tablename__ = "match_odds"
    __table_args__ = (
        UniqueConstraint(
            "match_id", "source", "bookmaker", "market", "line", "timing", "selection"
        ),
        CheckConstraint("price > 1", name="price_above_one"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    source: Mapped[DataSource] = mapped_column(_enum(DataSource, "data_source"))
    bookmaker: Mapped[str] = mapped_column(String(16))
    market: Mapped[str] = mapped_column(String(16))
    # Ligne du marché (2.5 pour over/under, handicap asiatique) ; 0 si sans objet.
    line: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="0")
    timing: Mapped[OddsTiming] = mapped_column(_enum(OddsTiming, "odds_timing"))
    selection: Mapped[str] = mapped_column(String(16))
    price: Mapped[Decimal] = mapped_column(Numeric(8, 3))


class IngestionRun(Base):
    """Journal d'une exécution d'ingestion, avec son rapport de qualité."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
