"""Prédictions : dernière prédiction d'un match, matchs à venir, exécutions du moteur.

Les probabilités sont celles du moteur ; aucune n'est comparée aux cotes pour
annoncer une « value » (principe n° 4, docs/MOTEUR.md).
"""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from footprono.api.deps import SessionDep
from footprono.api.v1.football import _match_out, _match_select
from footprono.core.errors import NotFoundError
from footprono.engine.markets import Selection
from footprono.football.models import Competition, Match, MatchStatus
from footprono.football.schemas import MatchOut
from footprono.predictions.models import MatchPrediction, PredictionRun
from footprono.predictions.schemas import (
    ExpectedGoals,
    PredictionOut,
    PredictionRunOut,
    PredictionSummary,
    SelectionOut,
    UpcomingMatchOut,
)

router = APIRouter(tags=["prédictions"])


def _selection(key: str, row: list[float]) -> SelectionOut:
    market, line, name = key.split("|")
    s = Selection(*row)
    return SelectionOut(
        market=market,
        line=line or None,
        selection=name,
        probability=s.win,
        half_win=s.half_win,
        push=s.push,
        half_loss=s.half_loss,
        fair_odds=None if s.fair_odds is None else round(s.fair_odds, 3),
    )


async def _latest(
    session: SessionDep, match_ids: list[int]
) -> dict[int, tuple[MatchPrediction, PredictionRun]]:
    """Dernière prédiction de chaque match (exécution la plus récente)."""
    if not match_ids:
        return {}
    latest = (
        select(MatchPrediction.match_id, func.max(MatchPrediction.run_id).label("run_id"))
        .where(MatchPrediction.match_id.in_(match_ids))
        .group_by(MatchPrediction.match_id)
        .subquery()
    )
    rows = await session.execute(
        select(MatchPrediction, PredictionRun)
        .join(
            latest,
            (latest.c.match_id == MatchPrediction.match_id)
            & (latest.c.run_id == MatchPrediction.run_id),
        )
        .join(PredictionRun, PredictionRun.id == MatchPrediction.run_id)
    )
    return {p.match_id: (p, r) for p, r in rows.tuples()}


@router.get("/matches/{match_id}/prediction", response_model=PredictionOut)
async def get_match_prediction(
    match_id: int,
    session: SessionDep,
    market: Annotated[str | None, Query(description="préfixe de marché, ex. 1X2, OU, AH")] = None,
) -> PredictionOut:
    found = (await _latest(session, [match_id])).get(match_id)
    if found is None:
        raise NotFoundError(f"aucune prédiction pour le match {match_id}")
    pred, run = found
    keys = sorted(pred.markets)
    if market:
        keys = [k for k in keys if k.split("|")[0] == market.upper()]
    return PredictionOut(
        match_id=match_id,
        run_id=run.id,
        engine_version=run.engine_version,
        as_of=run.as_of,
        created_at=pred.created_at,
        expected_goals=ExpectedGoals(home=pred.lambda_home, away=pred.lambda_away),
        markets=[_selection(k, pred.markets[k]) for k in keys],
        counts=pred.counts,
        context=pred.context,
    )


@router.get("/predictions/upcoming", response_model=list[UpcomingMatchOut])
async def list_upcoming(
    session: SessionDep,
    competition: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[UpcomingMatchOut]:
    start = date_from or datetime.now(UTC).date()
    end = date_to or start + timedelta(days=10)
    stmt = _match_select().where(
        Match.status == MatchStatus.SCHEDULED, Match.match_date >= start, Match.match_date <= end
    )
    if competition:
        stmt = stmt.where(Competition.code == competition.upper())
    rows = (
        (
            await session.execute(
                stmt.order_by(Match.match_date, Match.kickoff_time, Match.id).limit(limit)
            )
        )
        .tuples()
        .all()
    )
    latest = await _latest(session, [row[0].id for row in rows])
    out = []
    for row in rows:
        summary = None
        found = latest.get(row[0].id)
        if found is not None:
            pred, run = found
            m = pred.markets
            summary = PredictionSummary(
                run_id=run.id,
                engine_version=run.engine_version,
                created_at=pred.created_at,
                expected_goals=ExpectedGoals(home=pred.lambda_home, away=pred.lambda_away),
                home=_selection("1X2||home", m["1X2||home"]),
                draw=_selection("1X2||draw", m["1X2||draw"]),
                away=_selection("1X2||away", m["1X2||away"]),
                over_2_5=_selection("OU|2.5|over", m["OU|2.5|over"]),
                both_score=_selection("BTTS||yes", m["BTTS||yes"]),
            )
        out.append(UpcomingMatchOut(match=MatchOut(**_match_out(*row)), prediction=summary))
    return out


@router.get("/predictions/runs", response_model=list[PredictionRunOut])
async def list_prediction_runs(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[PredictionRun]:
    runs = await session.scalars(
        select(PredictionRun).order_by(PredictionRun.id.desc()).limit(limit)
    )
    return list(runs.all())
