"""Calcul et enregistrement des prédictions des matchs à venir.

Même code que le backtest (principe n° 2) : modèle des buts estimé avec les
matchs joués avant ``as_of``, correction apprise sur les prévisions hors
échantillon des saisons passées, puis loi des scores et marchés ; modèles des
corners, cartons et tirs. Rien n'est complété : un championnat sans assez
d'historique est signalé dans le rapport, pas prédit.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.engine import ENGINE_VERSION
from footprono.engine.backtest import BacktestConfig, run_backtest
from footprono.engine.context import TEAM_FEATURES, MatchContext, build_context
from footprono.engine.correction import DEFAULT_FEATURES, Correction, fit_correction
from footprono.engine.counts import (
    MARKET_NAMES,
    CountsModel,
    booking_points_markets,
    count_markets,
    counts_config,
    fit_counts,
    total_pmf,
)
from footprono.engine.goals import GoalsConfig, fit_goals
from footprono.engine.history import History, load_history
from footprono.engine.markets import Selection, derive_markets
from footprono.engine.scores import score_distribution
from footprono.football.models import Match
from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES
from footprono.predictions.models import MatchPrediction, PredictionRun

DEFAULT_DAYS_AHEAD = 10
PREDICTED_COUNTS = ("corners", "cards", "shots", "shots_on_target", "yellow_cards", "red_cards")


def _selection_row(s: Selection) -> list[float]:
    return [round(s.win, 6), round(s.half_win, 6), round(s.push, 6), round(s.half_loss, 6)]


def fit_live_correction(
    hist: History, as_of: np.datetime64, ctx: MatchContext, competitions: list[str]
) -> Correction:
    """Correction apprise sur toutes les prévisions hors échantillon avant ``as_of``."""
    first = int(hist.season.min()) + 1
    last = int(hist.season[hist.date < as_of].max())
    pred = run_backtest(hist, BacktestConfig(competitions, list(range(first, last + 1))))
    rows = np.array(pred.row, dtype=np.int64)
    keep = hist.date[rows] < as_of
    rows = rows[keep]
    lam_h, lam_a = np.array(pred.lam_h)[keep], np.array(pred.lam_a)[keep]
    return fit_correction(lam_h, lam_a, hist.hg[rows], hist.ag[rows], ctx, rows, DEFAULT_FEATURES)


def predict_match(
    hist: History,
    i: int,
    goals: Any,
    correction: Correction,
    ctx: MatchContext,
    counts: dict[str, CountsModel],
) -> dict[str, Any]:
    """Prédiction complète d'un match (ligne ``i`` de l'historique)."""
    home, away = int(hist.home[i]), int(hist.away[i])
    lam_h, lam_a = goals.rates(home, away)
    rows = np.array([i], dtype=np.int64)
    new_h, new_a = correction.apply(np.array([lam_h]), np.array([lam_a]), ctx, rows)
    lam_h, lam_a = float(new_h[0]), float(new_a[0])
    dist = score_distribution(lam_h, lam_a, goals.rho, goals.ht_share_home, goals.ht_share_away)
    markets = {k: _selection_row(s) for k, s in derive_markets(dist).items()}

    referee = str(hist.referee[i]) if len(hist.referee) else ""
    counts_out: dict[str, Any] = {}
    totals: dict[str, np.ndarray] = {}
    for stat, model in counts.items():
        mh, ma = model.means(home, away, referee)
        joint = model.joint(mh, ma)
        totals[stat] = total_pmf(joint)
        counts_out[stat] = {
            "mean_home": round(mh, 4),
            "mean_away": round(ma, 4),
            "size": round(model.size, 4),
            "referee_factor": round(model.referee_factor.get(referee, 1.0), 4) if referee else None,
        }
        if stat in MARKET_NAMES:
            markets.update({k: _selection_row(s) for k, s in count_markets(stat, joint).items()})
    if "yellow_cards" in totals and "red_cards" in totals:
        booking = booking_points_markets(totals["yellow_cards"], totals["red_cards"])
        markets.update({k: _selection_row(s) for k, s in booking.items()})

    context = {
        name: [float(ctx.team[name][0][i]), float(ctx.team[name][1][i])] for name in TEAM_FEATURES
    }
    context["season_progress"] = [float(ctx.progress[i])] * 2
    if ctx.rank is not None and ctx.points is not None:
        context["rank"] = [float(ctx.rank[0][i]), float(ctx.rank[1][i])]
        context["points"] = [float(ctx.points[0][i]), float(ctx.points[1][i])]
    return {
        "lambda_home": lam_h,
        "lambda_away": lam_a,
        "rho": goals.rho,
        "share_home": goals.ht_share_home,
        "share_away": goals.ht_share_away,
        "markets": markets,
        "counts": counts_out,
        "context": context,
        "referee": referee or None,
    }


async def predict_upcoming(
    session: AsyncSession,
    as_of: date | None = None,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    progress: Callable[[str], None] | None = None,
) -> PredictionRun:
    """Prédit les matchs non joués entre ``as_of`` et ``as_of + days_ahead``."""
    as_of = as_of or datetime.now(UTC).date()
    notify = progress or (lambda _m: None)
    run = PredictionRun(
        engine_version=ENGINE_VERSION,
        as_of=as_of,
        status="running",
        parameters={
            "days_ahead": days_ahead,
            "goals": GoalsConfig().__dict__,
            "correction_features": list(DEFAULT_FEATURES),
            "counts": {s: counts_config(s).__dict__ for s in PREDICTED_COUNTS},
        },
        report={},
    )
    session.add(run)
    await session.commit()

    hist = await load_history(session)
    day = np.datetime64(as_of, "D")
    end = day + np.timedelta64(days_ahead, "D")
    window = ~hist.finished & ~hist.excluded & (hist.date >= day) & (hist.date <= end)
    # Reportés, annulés ou arrêtés selon API-Football : pas de prédiction.
    unplayed = set(
        await session.scalars(select(Match.id).where(Match.api_status.in_(UNPLAYED_STATUSES)))
    )
    skipped = window & np.isin(hist.match_id, list(unplayed))
    upcoming = np.where(window & ~skipped)[0]
    competitions = sorted({str(c) for c in hist.competition[upcoming]})
    report: dict[str, Any] = {"competitions": {}, "errors": [], "postponed": int(skipped.sum())}
    notify(f"{len(upcoming)} matchs à prédire ({', '.join(competitions) or 'aucun'})")
    if len(upcoming):
        ctx = build_context(hist)
        notify("correction : apprentissage sur les saisons passées…")
        correction = fit_live_correction(hist, day, ctx, competitions)
        run.parameters = {**run.parameters, "correction": correction.coef}
        for comp in competitions:
            rows = upcoming[hist.competition[upcoming] == comp]
            try:
                goals = fit_goals(hist, comp, day)
                counts = {
                    s: fit_counts(hist, comp, s, day, counts_config(s)) for s in PREDICTED_COUNTS
                }
            except ValueError as exc:
                report["errors"].append(str(exc))
                continue
            for i in rows:
                values = predict_match(hist, int(i), goals, correction, ctx, counts)
                values.pop("referee")
                session.add(
                    MatchPrediction(run_id=run.id, match_id=int(hist.match_id[i]), **values)
                )
            report["competitions"][comp] = {
                "matches": len(rows),
                "trained_on": goals.n_matches,
                "home_advantage": round(goals.home_adv, 4),
                "rho": round(goals.rho, 4),
            }
            notify(f"{comp} : {len(rows)} matchs prédits")
    run.report = report
    run.status = "ok" if not report["errors"] else "partial"
    run.finished_at = datetime.now(UTC)
    await session.commit()
    return run
