"""Ligne de commande du moteur.

footprono-engine backtest --seasons 2022-2025
footprono-engine backtest --seasons 2022-2025 --half-life 365 --xg-weight 0.5
footprono-engine backtest --seasons 2022-2025 --grid    # compare plusieurs réglages
footprono-engine features --seasons 2019-2021           # teste chaque indicateur de contexte
footprono-engine counts                                 # corners, cartons, tirs
footprono-engine ah                                     # handicap asiatique contre les cotes
"""

import argparse
import asyncio
import itertools
import json
import sys
import time
from collections.abc import Sequence
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray

from footprono.core.config import get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.engine.backtest import (
    BacktestConfig,
    Predictions,
    ah_evaluation,
    apply_correction,
    counts_backtest,
    run_backtest,
    summarize,
)
from footprono.engine.context import TEAM_FEATURES, build_context
from footprono.engine.correction import DEFAULT_FEATURES
from footprono.engine.counts import counts_config
from footprono.engine.goals import GoalsConfig
from footprono.engine.history import History, load_history
from footprono.ingestion.cli import parse_competitions, parse_seasons
from footprono.ingestion.reference import COMPETITIONS
from footprono.predictions.service import predict_upcoming

FloatArray = NDArray[np.float64]


async def _predict(as_of: date | None, days: int) -> int:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            run = await predict_upcoming(session, as_of, days, progress=_progress)
    finally:
        await engine.dispose()
    print(f"Exécution {run.id} ({run.engine_version}) : {run.status}")
    for comp, info in run.report.get("competitions", {}).items():
        print(f"  {comp} : {info['matches']} matchs")
    for error in run.report.get("errors", []):
        print(f"  erreur : {error}")
    return 0 if run.status == "ok" else 1


async def _load() -> History:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            return await load_history(session)
    finally:
        await engine.dispose()


def _progress(message: str) -> None:
    print(f"  … {message}", file=sys.stderr, flush=True)


def _fmt(value: float | None) -> str:
    return "  -   " if value is None else f"{value:.4f}"


def _line(label: str, r: dict[str, Any]) -> str:
    m, nv = r["1x2"]["model"], r["1x2"]["naive"]
    vm = r["1x2_vs_market"]
    market = vm["market_close"]["log_loss"] if vm["market_close"] else None
    on_market = vm["model"]["log_loss"] if vm["model"] else None
    ou = r["ou25"]
    return (
        f"{label:<11} {r['n']:>5}  1X2 log loss {m['log_loss']:.4f} (naïf {nv['log_loss']:.4f}, "
        f"marché {_fmt(market)} vs modèle {_fmt(on_market)} sur {vm['n']})  "
        f"RPS {m['rps']:.4f} (naïf {nv['rps']:.4f})  "
        f"+2,5 {ou['model']['log_loss']:.4f} (naïf {ou['naive']['log_loss']:.4f}, "
        f"marché {_fmt(ou['vs_market']['market_close'])} vs {_fmt(ou['vs_market']['model'])})"
    )


def predict(
    hist: History,
    competitions: Sequence[str],
    seasons: Sequence[int],
    goals: GoalsConfig,
    features: Sequence[str] | None,
) -> Predictions:
    """Prévisions hors échantillon ; ``features`` None = modèle des buts brut.

    Avec correction, le modèle des buts est aussi rejoué sur les saisons
    antérieures : la correction de chaque saison apprend sur elles.
    """
    if features is None:
        return run_backtest(hist, BacktestConfig(competitions, seasons, goals, progress=_progress))
    first = int(hist.season.min()) + 1
    cfg = BacktestConfig(
        competitions, list(range(first, max(seasons) + 1)), goals, progress=_progress
    )
    pred = run_backtest(hist, cfg)
    pred = apply_correction(hist, pred, build_context(hist), features)
    return pred.select(np.isin(pred.season, list(seasons)))


def backtest(
    hist: History, args: argparse.Namespace, goals: GoalsConfig, verbose: bool
) -> dict[str, Any]:
    started = time.monotonic()
    features = None if args.no_correction else args.features
    pred = predict(hist, args.competitions, args.seasons, goals, features)
    report: dict[str, Any] = {
        "config": goals.__dict__,
        "correction": features,
        "overall": summarize(pred),
    }
    report["by_competition"] = {c: summarize(pred, c) for c in args.competitions}
    report["seconds"] = round(time.monotonic() - started, 1)
    if verbose and not args.json:
        for c, r in report["by_competition"].items():
            print(_line(c, r))
        print(_line("TOTAL", report["overall"]))
        ht = report["overall"].get("ht_1x2")
        if ht:
            model, naive = ht["model"]["log_loss"], ht["naive"]["log_loss"]
            print(f"Mi-temps 1X2 log loss {model:.4f} (naïf {naive:.4f})")
        b = report["overall"]["btts"]
        model, naive = b["model"]["log_loss"], b["naive"]["log_loss"]
        print(f"Les deux marquent log loss {model:.4f} (naïf {naive:.4f})")
        print("Calibration 1X2 (annoncé → observé) :")
        for row in report["overall"]["calibration_1x2"]:
            span = f"{row['from']:.1f}-{row['to']:.1f}"
            print(f"  {span}  n={row['n']:>5}  {row['announced']:.3f} → {row['observed']:.3f}")
        print(f"({report['seconds']} s)")
    return report


def _losses(pred: Predictions) -> FloatArray:
    """Pertes par match : log loss 1X2, +2,5 buts, les deux marquent."""
    n = len(pred.match_id)
    p1 = np.array(pred.model_1x2)[np.arange(n), np.array(pred.outcome_1x2)]
    yo, yb = np.array(pred.outcome_ou25), np.array(pred.outcome_btts)
    po, pb = np.array(pred.model_ou25), np.array(pred.model_btts)
    return -np.log(np.stack([p1, np.where(yo == 1, po, 1 - po), np.where(yb == 1, pb, 1 - pb)]))


def features_study(hist: History, args: argparse.Namespace) -> None:
    """Gain de chaque indicateur, un par un, contre la calibration seule.

    Gain = baisse moyenne de la log loss (positif = mieux) ± 2 erreurs types
    (comparaison appariée, match par match).
    """
    # Le modèle des buts ne dépend pas des indicateurs : calculé une seule fois.
    first = int(hist.season.min()) + 1
    cfg = BacktestConfig(
        args.competitions, list(range(first, max(args.seasons) + 1)), GoalsConfig(),
        progress=_progress,
    )  # fmt: skip
    raw = run_backtest(hist, cfg)
    ctx = build_context(hist)

    def losses(features: Sequence[str] | None) -> FloatArray:
        pred = raw if features is None else apply_correction(hist, raw, ctx, features)
        return _losses(pred.select(np.isin(pred.season, list(args.seasons))))

    base, calib = losses(None), losses(())
    rows: list[tuple[str, FloatArray]] = [("calibration", base - calib)]
    for f in TEAM_FEATURES:
        _progress(f"indicateur {f}")
        rows.append((f"+ {f}", calib - losses((f,))))
    print(f"{len(base[0])} matchs ; gain de log loss (positif = mieux) ± 2 erreurs types")
    print(f"{'':<16}{'1X2':>18}{'+2,5 buts':>18}{'deux marquent':>18}")
    for label, d in rows:
        se = 2 * d.std(axis=1) / np.sqrt(d.shape[1])
        cells = "".join(f"{m:>+10.4f} ±{e:.4f}" for m, e in zip(d.mean(axis=1), se, strict=True))
        print(f"{label:<16}{cells}")


EVALUATED_COUNTS = ("corners", "cards", "shots", "shots_on_target")


def counts_report(hist: History, args: argparse.Namespace) -> None:
    for stat in args.stats:
        _progress(f"{stat}…")
        r = counts_backtest(hist, args.competitions, args.seasons, stat, counts_config(stat))
        t, ou = r["total_log_loss"], r["ou_log_loss"]
        print(
            f"{stat:<16} {r['n']:>5}  total exact {t['model']:.4f} (naïf {t['naive']:.4f})  "
            f"plus/moins {r['line']:g} {ou['model']:.4f} (naïf {ou['naive']:.4f})",
            flush=True,
        )
        for row in r["ou_calibration"]:
            span = f"{row['from']:.1f}-{row['to']:.1f}"
            print(f"    {span}  n={row['n']:>5}  {row['announced']:.3f} → {row['observed']:.3f}")


def ah_report(hist: History, args: argparse.Namespace) -> None:
    pred = predict(hist, args.competitions, args.seasons, GoalsConfig(), DEFAULT_FEATURES)
    for timing, label in (("pre", "cotes d'avant-match"), ("close", "cotes de clôture")):
        r = ah_evaluation(hist, pred, timing)
        if not r["n"]:
            print(f"{label} : aucune cote de handicap asiatique")
            continue
        ll = r["log_loss"]
        print(
            f"{label} : {r['n']} matchs, log loss à la ligne du bookmaker "
            f"modèle {ll['model']:.4f}, marché {ll['market']:.4f} (pile ou face 0,6931)"
        )
        for b in r["betting"]:
            roi = (
                "  -  "
                if b["roi"] is None
                else f"{100 * b['roi']:+.1f} % ± {200 * b['roi_se']:.1f}"
            )
            print(
                f"    espérance modèle > {100 * b['threshold']:.0f} % : {b['bets']:>5} paris, {roi}"
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="footprono-engine")
    sub = parser.add_subparsers(dest="command", required=True)
    bt = sub.add_parser("backtest", help="évaluation stricte dans le temps")
    bt.add_argument("--seasons", type=parse_seasons, default=parse_seasons("2022-2025"))
    bt.add_argument(
        "--competitions", type=parse_competitions, default=[c.code for c in COMPETITIONS]
    )
    bt.add_argument("--half-life", type=float, default=GoalsConfig.half_life_days)
    bt.add_argument("--xg-weight", type=float, default=GoalsConfig.xg_weight)
    bt.add_argument("--ridge", type=float, default=GoalsConfig.ridge)
    bt.add_argument("--no-promoted-prior", action="store_true")
    bt.add_argument("--grid", action="store_true", help="compare plusieurs réglages")
    bt.add_argument("--no-correction", action="store_true", help="modèle des buts brut")
    bt.add_argument(
        "--features",
        type=lambda v: tuple(x for x in v.split(",") if x),
        default=DEFAULT_FEATURES,
        help=f"indicateurs de contexte ({', '.join(TEAM_FEATURES)})",
    )
    bt.add_argument("--json", action="store_true")
    fs = sub.add_parser("features", help="gain de chaque indicateur de contexte")
    fs.add_argument("--seasons", type=parse_seasons, default=parse_seasons("2019-2021"))
    fs.add_argument(
        "--competitions", type=parse_competitions, default=[c.code for c in COMPETITIONS]
    )
    cs = sub.add_parser("counts", help="corners, cartons et tirs")
    cs.add_argument("--seasons", type=parse_seasons, default=parse_seasons("2022-2025"))
    cs.add_argument(
        "--competitions", type=parse_competitions, default=[c.code for c in COMPETITIONS]
    )
    cs.add_argument(
        "--stats",
        type=lambda v: tuple(x for x in v.split(",") if x),
        default=EVALUATED_COUNTS,
        help=f"parmi {', '.join(EVALUATED_COUNTS)}",
    )
    ah = sub.add_parser("ah", help="handicap asiatique contre les cotes des bookmakers")
    ah.add_argument("--seasons", type=parse_seasons, default=parse_seasons("2022-2025"))
    ah.add_argument(
        "--competitions", type=parse_competitions, default=[c.code for c in COMPETITIONS]
    )
    pr = sub.add_parser("predict", help="prédit et enregistre les matchs à venir")
    pr.add_argument("--days", type=int, default=10, help="horizon en jours (défaut 10)")
    pr.add_argument("--as-of", type=date.fromisoformat, default=None, help="AAAA-MM-JJ")
    args = parser.parse_args(argv)

    if args.command == "predict":
        return asyncio.run(_predict(args.as_of, args.days))

    print("Chargement de l'historique…", file=sys.stderr, flush=True)
    hist = asyncio.run(_load())
    print(f"{len(hist)} matchs chargés ; calcul en cours.", file=sys.stderr, flush=True)
    if args.command == "features":
        features_study(hist, args)
        return 0
    if args.command == "ah":
        ah_report(hist, args)
        return 0
    if args.command == "counts":
        counts_report(hist, args)
        return 0
    if not args.grid:
        goals = GoalsConfig(
            half_life_days=args.half_life,
            xg_weight=args.xg_weight,
            ridge=args.ridge,
            promoted_prior=not args.no_promoted_prior,
        )
        report = backtest(hist, args, goals, verbose=True)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    results = []
    for half_life, xg_weight in itertools.product((180.0, 365.0, 730.0), (0.0, 0.4, 0.7)):
        goals = GoalsConfig(half_life_days=half_life, xg_weight=xg_weight, ridge=args.ridge)
        r = backtest(hist, args, goals, verbose=False)["overall"]
        results.append((r["1x2"]["model"]["log_loss"], half_life, xg_weight, r))
        m = r["1x2"]["model"]
        print(
            f"demi-vie {half_life:>5.0f} j  xG {xg_weight:.1f}  1X2 {m['log_loss']:.4f}  "
            f"RPS {m['rps']:.4f}  +2,5 {r['ou25']['model']['log_loss']:.4f}",
            flush=True,
        )
    best = min(results, key=lambda t: t[0])
    print(f"Meilleur : demi-vie {best[1]:.0f} j, poids xG {best[2]:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
