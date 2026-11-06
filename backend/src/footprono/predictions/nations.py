"""Pronostics des sélections nationales (moteur ``engine/nations.py``), enregistrés avant
les matchs officiels : ils comptent sur la page Fiabilité comme ceux des championnats.

Le backtest (calculé sur les données en base) est gardé dans les réglages du serveur
(``nations_backtest``) et montré à part sur la page Fiabilité."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.console.models import AppSetting
from footprono.engine import nations as engine
from footprono.football.models import Match
from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES
from footprono.predictions.models import MatchPrediction, PredictionRun
from footprono.predictions.service import _selection_row

BACKTEST_KEY = "nations_backtest"
BACKTEST_FIRST_YEAR = 2021


async def predict_nations(
    session: AsyncSession, as_of: date | None = None, days_ahead: int = 10
) -> PredictionRun:
    as_of = as_of or datetime.now(UTC).date()
    run = PredictionRun(
        engine_version=engine.ENGINE_VERSION, as_of=as_of, status="running",
        parameters={
            "days_ahead": days_ahead, "k": [engine.K_OFFICIAL, engine.K_FRIENDLY],
            "home": engine.HOME, "level_rate": engine.LEVEL_RATE,
            "window_years": engine.WINDOW_YEARS, "max_favourite": engine.MAX_FAVOURITE,
        },
        report={},
    )  # fmt: skip
    session.add(run)
    await session.commit()
    matches = await engine.load_matches(session)
    unplayed = set(
        await session.scalars(select(Match.id).where(Match.api_status.in_(UNPLAYED_STATUSES)))
    )
    end = as_of + timedelta(days=days_ahead)
    upcoming = [
        m for m in matches
        if engine.official(m.competition) and not m.finished and as_of <= m.day <= end
        and m.match_id not in unplayed
    ]  # fmt: skip
    report: dict[str, Any] = {"matches": 0, "favourites": 0, "competitions": {}, "errors": []}
    if upcoming:
        state = engine.build_state(matches, as_of)
        try:
            model = engine.fit_model(state.samples, as_of.year)
        except ValueError as exc:
            report["errors"].append(str(exc))
            upcoming = []
        features = [state.features(m) for m in upcoming]
        preds = engine.predict(model, features) if upcoming else []
        for m, p in zip(upcoming, preds, strict=True):
            if p is None:  # favori écrasant : pas de pronostic
                report["favourites"] += 1
                continue
            session.add(
                MatchPrediction(
                    run_id=run.id, match_id=m.match_id,
                    lambda_home=p.lambda_home, lambda_away=p.lambda_away, rho=model.rho,
                    share_home=model.share_home, share_away=model.share_away,
                    markets={k: _selection_row(s) for k, s in p.markets.items()},
                    counts={},
                    context={"nations": {
                        "rating_home": round(state.rating(m.home), 1),
                        "rating_away": round(state.rating(m.away), 1),
                        "neutral": m.neutral,
                    }},
                )
            )  # fmt: skip
            report["competitions"][m.competition] = report["competitions"].get(m.competition, 0) + 1
            report["matches"] += 1
        if upcoming:
            report["model"] = {
                "year": model.year, "training_matches": model.matches, "rho": round(model.rho, 4),
            }  # fmt: skip
    run.report = report
    run.status = "ok" if not report["errors"] else "partial"
    run.finished_at = datetime.now(UTC)
    await session.commit()
    return run


async def refresh_backtest(session: AsyncSession, today: date | None = None) -> dict[str, Any]:
    """Backtest des sélections sur les données en base, gardé pour la page Fiabilité."""
    today = today or datetime.now(UTC).date()
    result = engine.backtest(await engine.load_matches(session), BACKTEST_FIRST_YEAR, today.year)
    value = {
        "label": "Backtest des sélections nationales : simulation sur des années passées",
        "verified_on": today.isoformat(),
        "seasons": f"{BACKTEST_FIRST_YEAR} à aujourd'hui (matchs officiels)",
        "matches": result.matches,
        "engine_version": engine.ENGINE_VERSION,
        "log_loss": {k: {**v, "closing_odds": None} for k, v in result.log_loss.items()},
        "by_competition": result.by_competition,
        "by_year": result.years,
        "hit_rate": result.hit_rate,
        "calibration_1x2": result.calibration,
        "note": (
            "Sélections nationales : moteur à part (note Elo, niveaux de buts), matchs "
            "officiels seulement (les amicaux servent aux notes). Favoris écrasants (une "
            f"équipe à 90 % ou plus : {result.skipped_favourites} matchs) : pas de "
            "pronostic. Pas d'historique de cotes : pas de comparaison au marché."
        ),
    }
    row = await session.get(AppSetting, BACKTEST_KEY)
    if row is None:
        session.add(AppSetting(key=BACKTEST_KEY, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)
    await session.commit()
    return value


async def stored_backtest(session: AsyncSession) -> dict[str, Any] | None:
    row = await session.get(AppSetting, BACKTEST_KEY)
    return json.loads(row.value) if row else None
