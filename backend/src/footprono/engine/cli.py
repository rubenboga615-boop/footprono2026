"""Ligne de commande du moteur.

footprono-engine backtest --seasons 2022-2025
footprono-engine backtest --seasons 2022-2025 --half-life 365 --xg-weight 0.5
footprono-engine backtest --seasons 2022-2025 --grid    # compare plusieurs réglages
"""

import argparse
import asyncio
import itertools
import json
import sys
import time
from collections.abc import Sequence
from typing import Any

from footprono.core.config import get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.engine.backtest import BacktestConfig, run_backtest, summarize
from footprono.engine.goals import GoalsConfig
from footprono.engine.history import History, load_history
from footprono.ingestion.cli import parse_competitions, parse_seasons
from footprono.ingestion.reference import COMPETITIONS


async def _load() -> History:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            return await load_history(session)
    finally:
        await engine.dispose()


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


def backtest(
    hist: History, args: argparse.Namespace, goals: GoalsConfig, verbose: bool
) -> dict[str, Any]:
    cfg = BacktestConfig(competitions=args.competitions, seasons=args.seasons, goals=goals)
    started = time.monotonic()
    pred = run_backtest(hist, cfg)
    report: dict[str, Any] = {"config": goals.__dict__, "overall": summarize(pred)}
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
    bt.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    hist = asyncio.run(_load())
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
