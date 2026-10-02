"""Lecture des données sportives : compétitions, équipes, matchs, ingestions."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import aliased

from footprono.accounts.plans import PremiumRequiredError, is_premium
from footprono.api.deps import OptionalUserDep, SessionDep
from footprono.core.errors import NotFoundError
from footprono.football.analysis import match_analysis
from footprono.football.models import (
    BookmakerOdds,
    Competition,
    IngestionRun,
    Match,
    MatchAdvancedStats,
    MatchOdds,
    MatchStatus,
    MatchTeamSheet,
    MatchTeamStats,
    Season,
    Team,
)
from footprono.football.referees import referee_profile, referee_table
from footprono.football.schemas import (
    AdvancedStatsOut,
    BookmakerOddsOut,
    CompetitionOut,
    IngestionRunDetailOut,
    IngestionRunOut,
    MatchDetailOut,
    MatchOut,
    MatchPage,
    MatchStatsOut,
    OddsOut,
    SeasonOut,
    TeamOut,
    TeamStatsOut,
)
from footprono.football.team_stats import lock_premium, merited_table, team_profile
from footprono.ingestion.live import LIVE_STATUSES
from footprono.ingestion.quality import run_quality_checks
from footprono.ingestion.sources.api_football_odds import REFERENCE_ONLY, map_bet

router = APIRouter(tags=["données"])

_Home = aliased(Team, name="home")
_Away = aliased(Team, name="away")


def _match_select() -> Select[tuple[Match, Team, Team, str, int]]:
    return (
        select(Match, _Home, _Away, Competition.code, Season.start_year)
        .join(Season, Season.id == Match.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .join(_Home, _Home.id == Match.home_team_id)
        .join(_Away, _Away.id == Match.away_team_id)
    )


def _match_out(match: Match, home: Team, away: Team, code: str, year: int) -> dict[str, Any]:
    return {
        "id": match.id,
        "competition": code,
        "season": year,
        "match_date": match.match_date,
        "kickoff_time": match.kickoff_time,
        "kickoff_at": match.kickoff_at,
        "status": match.status,
        "api_status": match.api_status,
        "home_team": TeamOut.model_validate(home),
        "away_team": TeamOut.model_validate(away),
        "home_goals": match.home_goals,
        "away_goals": match.away_goals,
        "result_source": match.result_source,
        "live_minute": match.live_minute,
        "live_home_goals": match.live_home_goals,
        "live_away_goals": match.live_away_goals,
    }


@router.get("/competitions", response_model=list[CompetitionOut])
async def list_competitions(session: SessionDep) -> list[CompetitionOut]:
    competitions = (await session.scalars(select(Competition).order_by(Competition.id))).all()
    rows = await session.execute(
        select(
            Season.competition_id,
            Season.start_year,
            func.count(Match.id),
            func.count(Match.id).filter(Match.status == MatchStatus.FINISHED),
        )
        .outerjoin(Match, Match.season_id == Season.id)
        .group_by(Season.id)
        .order_by(Season.start_year)
    )
    seasons: dict[int, list[SeasonOut]] = {}
    for comp_id, year, n, finished in rows.tuples():
        label = f"{year}-{(year + 1) % 100:02d}"
        seasons.setdefault(comp_id, []).append(
            SeasonOut(start_year=year, label=label, matches=n, finished=finished)
        )
    return [
        CompetitionOut(
            code=c.code,
            name=c.name,
            country=c.country,
            n_teams=c.n_teams,
            seasons=seasons.get(c.id, []),
        )
        for c in competitions
    ]


@router.get("/competitions/{code}/seasons/{year}/teams", response_model=list[TeamOut])
async def list_season_teams(code: str, year: int, session: SessionDep) -> list[Team]:
    season_id = await session.scalar(
        select(Season.id)
        .join(Competition, Competition.id == Season.competition_id)
        .where(Competition.code == code.upper(), Season.start_year == year)
    )
    if season_id is None:
        raise NotFoundError(f"saison {year} de {code} absente de la base")
    team_ids = (
        select(Match.home_team_id)
        .where(Match.season_id == season_id)
        .union(select(Match.away_team_id).where(Match.season_id == season_id))
    )
    return list(
        (await session.scalars(select(Team).where(Team.id.in_(team_ids)).order_by(Team.name))).all()
    )


@router.get("/teams/{team_id}", response_model=TeamOut)
async def get_team(team_id: int, session: SessionDep) -> Team:
    team = await session.get(Team, team_id)
    if team is None:
        raise NotFoundError(f"équipe {team_id} introuvable")
    return team


@router.get("/teams/{team_id}/profile")
async def get_team_profile(
    team_id: int,
    session: SessionDep,
    user: OptionalUserDep,
    competition: str | None = None,
    season: int | None = None,
) -> dict[str, Any]:
    """Fiche équipe : forme, bilan domicile / extérieur (statistiques avancées : Premium)."""
    profile = await team_profile(session, team_id, competition, season)
    profile["locked"] = False
    return profile if is_premium(user) else lock_premium(profile)


@router.get("/competitions/{code}/seasons/{year}/merited")
async def get_merited_table(code: str, year: int, session: SessionDep) -> dict[str, Any]:
    """Classement réel contre classement mérité (xPts Understat)."""
    return await merited_table(session, code, year)


@router.get("/referees/profile")
async def get_referee_profile(
    session: SessionDep, name: Annotated[str, Query(min_length=2, max_length=100)]
) -> dict[str, Any]:
    """Fiche arbitre : cartons par match contre la moyenne du championnat, saison par saison."""
    return await referee_profile(session, name)


@router.get("/competitions/{code}/seasons/{year}/referees")
async def get_referee_table(code: str, year: int, session: SessionDep) -> dict[str, Any]:
    """Arbitres d'une saison, du plus sévère au plus clément (cartons jaunes par match)."""
    return await referee_table(session, code, year)


@router.get("/matches", response_model=MatchPage)
async def list_matches(
    session: SessionDep,
    competition: str | None = None,
    season: Annotated[int | None, Query(description="année de début de saison")] = None,
    team_id: int | None = None,
    status: MatchStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MatchPage:
    stmt = _match_select()
    if competition:
        stmt = stmt.where(Competition.code == competition.upper())
    if season is not None:
        stmt = stmt.where(Season.start_year == season)
    if team_id is not None:
        stmt = stmt.where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if status is not None:
        stmt = stmt.where(Match.status == status)
    if date_from is not None:
        stmt = stmt.where(Match.match_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Match.match_date <= date_to)

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await session.execute(
        stmt.order_by(Match.match_date, Match.kickoff_time, Match.id).limit(limit).offset(offset)
    )
    return MatchPage(
        items=[MatchOut(**_match_out(*row)) for row in rows.tuples()],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/live", response_model=list[MatchOut])
async def list_live(session: SessionDep) -> list[MatchOut]:
    """Matchs en cours selon le dernier passage du suivi en direct."""
    rows = await session.execute(
        _match_select()
        .where(Match.status == MatchStatus.SCHEDULED, Match.api_status.in_(LIVE_STATUSES))
        .order_by(Match.kickoff_at, Match.id)
    )
    return [MatchOut(**_match_out(*row)) for row in rows.tuples()]


@router.get("/matches/{match_id}", response_model=MatchDetailOut)
async def get_match(match_id: int, session: SessionDep) -> MatchDetailOut:
    row = (await session.execute(_match_select().where(Match.id == match_id))).tuples().first()
    if row is None:
        raise NotFoundError(f"match {match_id} introuvable")
    match = row[0]
    advanced = await session.scalars(
        select(MatchAdvancedStats)
        .where(MatchAdvancedStats.match_id == match_id)
        .order_by(MatchAdvancedStats.source, MatchAdvancedStats.team_id)
    )
    team_stats = await session.scalars(
        select(MatchTeamStats)
        .where(MatchTeamStats.match_id == match_id)
        .order_by(MatchTeamStats.source, MatchTeamStats.period, MatchTeamStats.team_id)
    )
    odds = await session.scalars(
        select(MatchOdds)
        .where(MatchOdds.match_id == match_id)
        .order_by(
            MatchOdds.market,
            MatchOdds.line,
            MatchOdds.timing,
            MatchOdds.bookmaker,
            MatchOdds.selection,
        )
    )
    return MatchDetailOut(
        **_match_out(*row),
        stats=MatchStatsOut.model_validate(match),
        api_football_id=match.api_football_id,
        advanced_stats=[AdvancedStatsOut.model_validate(a) for a in advanced],
        team_stats=[TeamStatsOut.model_validate(t) for t in team_stats],
        odds=[OddsOut.model_validate(o) for o in odds],
        updated_at=match.updated_at,
    )


@router.get("/matches/{match_id}/bookmaker-odds", response_model=list[BookmakerOddsOut])
async def get_bookmaker_odds(
    match_id: int,
    session: SessionDep,
    include_reference: Annotated[
        bool, Query(description="inclure les bookmakers de référence interne (Pinnacle)")
    ] = False,
) -> list[BookmakerOddsOut]:
    """Dernière cote de chaque bookmaker pour ce match (pas de comparaison « value »)."""
    last = (
        select(func.max(BookmakerOdds.id))
        .where(BookmakerOdds.match_id == match_id)
        .group_by(BookmakerOdds.bookmaker, BookmakerOdds.bet, BookmakerOdds.value)
    )
    rows = await session.scalars(
        select(BookmakerOdds)
        .where(BookmakerOdds.id.in_(last))
        .order_by(BookmakerOdds.bookmaker, BookmakerOdds.bet, BookmakerOdds.value)
    )
    out = []
    for o in rows:
        if o.bookmaker in REFERENCE_ONLY and not include_reference:
            continue
        mapped = map_bet(o.bet, o.value)
        market, line, selection = mapped if mapped else (None, None, None)
        out.append(
            BookmakerOddsOut(
                bookmaker=o.bookmaker,
                bet=o.bet,
                value=o.value,
                price=o.price,
                market=market,
                line=line or None,
                selection=selection,
                fetched_at=o.fetched_at,
                source_updated_at=o.source_updated_at,
            )
        )
    return out


@router.get("/matches/{match_id}/team-sheets")
async def get_team_sheets(match_id: int, session: SessionDep) -> dict[str, Any]:
    """Compositions et blessés publiés par API-Football (à titre d'information :
    le moteur ne les utilise pas)."""
    sheets = await session.scalars(
        select(MatchTeamSheet).where(MatchTeamSheet.match_id == match_id)
    )
    return {s.kind: {"fetched_at": s.fetched_at, "data": s.payload} for s in sheets}


@router.get("/ingestion/runs", response_model=list[IngestionRunOut])
async def list_ingestion_runs(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[IngestionRun]:
    runs = await session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit))
    return list(runs.all())


@router.get("/ingestion/runs/{run_id}", response_model=IngestionRunDetailOut)
async def get_ingestion_run(run_id: int, session: SessionDep) -> IngestionRun:
    run = await session.get(IngestionRun, run_id)
    if run is None:
        raise NotFoundError(f"ingestion {run_id} introuvable")
    return run


@router.get("/data/quality")
async def data_quality(session: SessionDep) -> dict[str, Any]:
    """Contrôles de qualité recalculés sur l'état actuel de la base."""
    return await run_quality_checks(session)


@router.get("/matches/{match_id}/analysis")
async def get_match_analysis(
    match_id: int, session: SessionDep, user: OptionalUserDep
) -> dict[str, Any]:
    """Forme (5 derniers matchs), confrontations directes, moyennes de la saison.

    Analyse détaillée : réservée à Premium (comme l'onglet Analyse).
    """
    if not is_premium(user):
        raise PremiumRequiredError("analyse détaillée du match : réservée à Premium")
    return await match_analysis(session, match_id)
