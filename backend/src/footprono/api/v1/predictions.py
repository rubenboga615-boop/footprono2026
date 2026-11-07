"""Prédictions : dernière prédiction d'un match, matchs à venir, exécutions du moteur.

Les probabilités sont celles du moteur ; aucune n'est comparée aux cotes pour
annoncer une « value » (principe n° 4, docs/MOTEUR.md).
"""

import contextlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi.encoders import jsonable_encoder
from redis.exceptions import RedisError
from sqlalchemy import func, select

from footprono.accounts.plans import FREE_MARKETS, is_premium
from footprono.api.deps import OptionalUserDep, RedisDep, SessionDep, SettingsDep
from footprono.api.v1.football import _match_out, _match_select
from footprono.core.errors import NotFoundError
from footprono.engine.markets import Selection, offered
from footprono.football.models import Competition, Match, MatchStatus
from footprono.football.schemas import MatchOut
from footprono.ingestion.reference import CUPS_BY_CODE, NATIONS_BY_CODE
from footprono.predictions.models import MatchPrediction, PredictionRun
from footprono.predictions.publication import publication
from footprono.predictions.reliability import cache_key, reliability_report
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


def _expected(pred: MatchPrediction) -> ExpectedGoals | None:
    """Buts attendus ; aucun pour les pronostics de coupe d'avant le moteur coupes 2.0."""
    if pred.lambda_home <= 0 and pred.lambda_away <= 0:
        return None
    return ExpectedGoals(home=pred.lambda_home, away=pred.lambda_away)


@router.get("/matches/{match_id}/prediction", response_model=PredictionOut)
async def get_match_prediction(
    match_id: int,
    session: SessionDep,
    user: OptionalUserDep,
    market: Annotated[str | None, Query(description="préfixe de marché, ex. 1X2, OU, AH")] = None,
) -> PredictionOut:
    found = (await _latest(session, [match_id])).get(match_id)
    if found is None:
        raise NotFoundError(f"aucune prédiction pour le match {match_id}")
    pred, run = found
    premium = is_premium(user)
    keys = sorted(k for k in pred.markets if offered(k))
    locked = sorted({k.split("|")[0] for k in keys} - FREE_MARKETS) if not premium else []
    if not premium:
        keys = [k for k in keys if k.split("|")[0] in FREE_MARKETS]
    if market:
        keys = [k for k in keys if k.split("|")[0] == market.upper()]
    return PredictionOut(
        match_id=match_id,
        run_id=run.id,
        engine_version=run.engine_version,
        as_of=run.as_of,
        created_at=pred.created_at,
        expected_goals=_expected(pred),
        markets=[_selection(k, pred.markets[k]) for k in keys],
        counts=pred.counts if premium else None,
        context=pred.context if premium else None,
        plan="premium" if premium else "free",
        locked_markets=locked,
    )


@router.get("/predictions/upcoming", response_model=list[UpcomingMatchOut])
async def list_upcoming(
    session: SessionDep,
    settings: SettingsDep,
    competition: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cups: Annotated[
        bool, Query(description="inclure les coupes d'Europe (application qui sait les afficher)")
    ] = False,
    nations: Annotated[
        bool, Query(description="inclure les sélections nationales (matchs officiels pronostiqués)")
    ] = False,
) -> list[UpcomingMatchOut]:
    start = date_from or datetime.now(UTC).date()
    end = date_to or start + timedelta(days=10)
    published = await publication(session, settings)
    stmt = _match_select().where(
        Match.status == MatchStatus.SCHEDULED, Match.match_date >= start, Match.match_date <= end
    )
    if competition:
        stmt = stmt.where(Competition.code == competition.upper())
    elif not cups or not published.cups:
        # Les applications d'avant les coupes attendent toujours « plus/moins 2,5 » et les
        # buts attendus : elles ne reçoivent pas les matchs de coupe. Pronostics des coupes
        # désactivés (console, Moteur) : pas de matchs de coupe sans pronostic.
        stmt = stmt.where(Competition.code.not_in(list(CUPS_BY_CODE)))
    show_nations = bool(competition) or (nations and published.nations)
    if not show_nations:
        # Sélections : demandées par l'application qui les affiche, pronostics activés
        # (interrupteur de la console).
        stmt = stmt.where(Competition.code.not_in(list(NATIONS_BY_CODE)))
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
        if found is None and row[3] in NATIONS_BY_CODE and not competition:
            # Sélections : amicaux et favoris écrasants ne sont jamais pronostiqués.
            continue
        if found is not None:
            pred, run = found
            m = pred.markets
            summary = PredictionSummary(
                run_id=run.id,
                engine_version=run.engine_version,
                created_at=pred.created_at,
                expected_goals=_expected(pred),
                home=_selection("1X2||home", m["1X2||home"]),
                draw=_selection("1X2||draw", m["1X2||draw"]),
                away=_selection("1X2||away", m["1X2||away"]),
                over_2_5=_selection("OU|2.5|over", m["OU|2.5|over"])
                if "OU|2.5|over" in m
                else None,
                both_score=_selection("BTTS||yes", m["BTTS||yes"]) if "BTTS||yes" in m else None,
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


@router.get("/reliability")
async def reliability(
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    competition: str | None = None,
    since: Annotated[date | None, Query(description="matchs joués à partir de cette date")] = None,
    recent: Annotated[int, Query(ge=0, le=100)] = 20,
) -> Any:
    """Fiabilité publique : prédictions faites avant les matchs face aux résultats (gratuit).

    Calcul gardé quelques minutes (6 à 7 s à chaque ouverture en production, essai du
    06/11/2026) : les chiffres ne changent qu'au règlement des matchs."""
    code = competition.upper() if competition else None
    ttl = settings.reliability_cache_seconds
    key = cache_key(code, since, recent)  # vues par défaut préparées par le worker
    cached = None
    if ttl > 0:
        with contextlib.suppress(RedisError):  # Redis indisponible : calcul direct
            cached = await redis.get(key)
    if cached is not None:
        return Response(content=cached, media_type="application/json")
    report = jsonable_encoder(
        await reliability_report(session, competition=code, since=since, recent=recent)
    )
    if ttl > 0:
        with contextlib.suppress(RedisError):
            await redis.set(key, json.dumps(report), ex=ttl)
    return report
