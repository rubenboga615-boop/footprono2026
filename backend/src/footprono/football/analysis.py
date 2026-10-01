"""Analyse factuelle d'un match : forme, confrontations, moyennes de la saison.

Uniquement des faits tirés des matchs déjà joués **avant** ce match (aucune
estimation : les estimations sont dans la prédiction du moteur). Sources :
résultats et statistiques football-data, xG Understat.
"""

from datetime import date
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from footprono.core.errors import NotFoundError
from footprono.football.models import (
    Competition,
    DataSource,
    Match,
    MatchAdvancedStats,
    MatchStatus,
    Season,
    Team,
)

FORM_MATCHES = 5
H2H_MATCHES = 5


def _result(goals_for: int, goals_against: int) -> str:
    return "W" if goals_for > goals_against else ("D" if goals_for == goals_against else "L")


def _played_before(day: date) -> Any:
    return and_(
        Match.status == MatchStatus.FINISHED,
        Match.home_goals.is_not(None),
        Match.away_goals.is_not(None),
        Match.match_date < day,
    )


async def _form(session: AsyncSession, team_id: int, day: date) -> list[dict[str, Any]]:
    home, away = aliased(Team), aliased(Team)
    rows = await session.execute(
        select(Match, home.name, away.name, Competition.code)
        .join(home, home.id == Match.home_team_id)
        .join(away, away.id == Match.away_team_id)
        .join(Season, Season.id == Match.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .where(
            _played_before(day), or_(Match.home_team_id == team_id, Match.away_team_id == team_id)
        )
        .order_by(Match.match_date.desc(), Match.id.desc())
        .limit(FORM_MATCHES)
    )
    out = []
    for m, home_name, away_name, comp in rows.tuples():
        at_home = m.home_team_id == team_id
        gf, ga = (m.home_goals, m.away_goals) if at_home else (m.away_goals, m.home_goals)
        assert gf is not None
        assert ga is not None
        out.append(
            {
                "match_id": m.id,
                "date": m.match_date,
                "competition": comp,
                "venue": "home" if at_home else "away",
                "opponent": away_name if at_home else home_name,
                "score": f"{m.home_goals}-{m.away_goals}",
                "result": _result(gf, ga),
            }
        )
    return out


async def _head_to_head(session: AsyncSession, a: int, b: int, day: date) -> list[dict[str, Any]]:
    home, away = aliased(Team), aliased(Team)
    rows = await session.execute(
        select(Match, home.name, away.name, Competition.code)
        .join(home, home.id == Match.home_team_id)
        .join(away, away.id == Match.away_team_id)
        .join(Season, Season.id == Match.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .where(
            _played_before(day),
            or_(
                and_(Match.home_team_id == a, Match.away_team_id == b),
                and_(Match.home_team_id == b, Match.away_team_id == a),
            ),
        )
        .order_by(Match.match_date.desc(), Match.id.desc())
        .limit(H2H_MATCHES)
    )
    return [
        {
            "match_id": m.id,
            "date": m.match_date,
            "competition": comp,
            "home": home_name,
            "away": away_name,
            "score": f"{m.home_goals}-{m.away_goals}",
            "winner": (
                "draw"
                if m.home_goals == m.away_goals
                else (home_name if (m.home_goals or 0) > (m.away_goals or 0) else away_name)
            ),
        }
        for m, home_name, away_name, comp in rows.tuples()
    ]


def _avg(total: Any, n: int) -> float | None:
    return None if total is None or n == 0 else round(float(total) / n, 2)


async def _season_averages(
    session: AsyncSession, team_id: int, season_id: int, day: date
) -> dict[str, Any]:
    """Moyennes par match de l'équipe cette saison (championnat), avant ce match."""
    is_home = Match.home_team_id == team_id
    played = and_(
        _played_before(day),
        Match.season_id == season_id,
        or_(is_home, Match.away_team_id == team_id),
    )

    def own(home_col: Any, away_col: Any) -> Any:
        return case((is_home, home_col), else_=away_col)

    row = (
        await session.execute(
            select(
                func.count(Match.id),
                func.sum(own(Match.home_goals, Match.away_goals)),
                func.sum(own(Match.away_goals, Match.home_goals)),
                func.sum(own(Match.home_shots_on_target, Match.away_shots_on_target)),
                func.count(own(Match.home_shots_on_target, Match.away_shots_on_target)),
                func.sum(own(Match.home_corners, Match.away_corners)),
                func.count(own(Match.home_corners, Match.away_corners)),
            ).where(played)
        )
    ).one()
    n, gf, ga, sot, n_sot, corners, n_corners = row
    xg_row = (
        await session.execute(
            select(
                func.count(MatchAdvancedStats.id),
                func.sum(MatchAdvancedStats.xg),
                func.sum(MatchAdvancedStats.xga),
            )
            .join(Match, Match.id == MatchAdvancedStats.match_id)
            .where(
                played,
                MatchAdvancedStats.team_id == team_id,
                MatchAdvancedStats.source == DataSource.UNDERSTAT,
                MatchAdvancedStats.xg.is_not(None),
            )
        )
    ).one()
    n_xg, xg, xga = xg_row
    return {
        "matches": n,
        "goals_for": _avg(gf, n),
        "goals_against": _avg(ga, n),
        "xg_for": _avg(xg, n_xg),
        "xg_against": _avg(xga, n_xg),
        "shots_on_target": _avg(sot, n_sot),
        "corners": _avg(corners, n_corners),
    }


async def match_analysis(session: AsyncSession, match_id: int) -> dict[str, Any]:
    match = await session.get(Match, match_id)
    if match is None:
        raise NotFoundError(f"match {match_id} introuvable")
    day = match.match_date
    h, a = match.home_team_id, match.away_team_id
    return {
        "match_id": match.id,
        "rule": "Faits tirés des seuls matchs joués avant celui-ci.",
        "form": {"home": await _form(session, h, day), "away": await _form(session, a, day)},
        "head_to_head": await _head_to_head(session, h, a, day),
        "season": {
            "home": await _season_averages(session, h, match.season_id, day),
            "away": await _season_averages(session, a, match.season_id, day),
        },
    }
