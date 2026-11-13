"""Suivi et analyse des montantes (maquettes M1 à M5 validées le 13/11/2026).

- ``player_summary`` (M1, M2) : bilan d'un joueur, gagnées et perdues ensemble ; jusqu'où
  vont ses montantes comparé aux cotes ; où elles s'arrêtent ; ses choix (paliers proposés
  par le moteur ou composés lui-même, cote hors plage) ; ses marchés.
- ``reliability`` (M4) : pour tous les joueurs, sans nom : chance du moteur des paris de
  palier contre ce qui est arrivé ; montantes allées au bout contre l'attendu selon les
  cotes ; bilan en argent, mises de départ comprises. Verdict seulement à partir de
  ``MIN_FINISHED`` montantes terminées.
- ``console_overview`` (M5) : état de toutes les montantes et anomalies à regarder.

Chiffres réels uniquement ; « selon les cotes » : produit des 1/cote (marge du bookmaker
comprise), cote jouée pour un palier joué, milieu de plage sinon.
"""

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.montante import plan
from footprono.bookmaker.montante_models import Montante, MontanteStep
from footprono.football.models import Match

MIN_FINISHED = 30  # montantes terminées avant d'afficher un verdict (décision du 13/11)
FINISHED = ("completed", "lost", "cashed_out")
WON_STEPS = ("won", "partial")


async def _load(
    session: AsyncSession, user_id: int | None = None, since: datetime | None = None
) -> list[tuple[Montante, list[MontanteStep], dict[int, Bet]]]:
    query = select(Montante).order_by(Montante.id)
    if user_id is not None:
        query = query.where(Montante.user_id == user_id)
    if since is not None:
        query = query.where(Montante.created_at >= since)
    montantes = list(await session.scalars(query))
    if not montantes:
        return []
    steps: dict[int, list[MontanteStep]] = defaultdict(list)
    for s in await session.scalars(
        select(MontanteStep)
        .where(MontanteStep.montante_id.in_([m.id for m in montantes]))
        .order_by(MontanteStep.montante_id, MontanteStep.number)
    ):
        steps[s.montante_id].append(s)
    bet_ids = [s.bet_id for rows in steps.values() for s in rows if s.bet_id]
    bets = (
        {b.id: b for b in await session.scalars(select(Bet).where(Bet.id.in_(bet_ids)))}
        if bet_ids
        else {}
    )
    return [(m, steps[m.id], bets) for m in montantes]


def _odds(step: MontanteStep, bets: dict[int, Bet]) -> float:
    bet = bets.get(step.bet_id) if step.bet_id else None
    if bet is not None:
        return float(bet.total_odds)
    return float((step.odds_min + step.odds_max) / 2)


def _reached(m: Montante, steps: list[MontanteStep]) -> int:
    """Dernier palier atteint (1 = le premier) ; une montante réussie les atteint tous."""
    if m.status == "completed":
        return len(steps)
    return min(m.current_step, len(steps))


def _expected_reach(steps: list[MontanteStep], bets: dict[int, Bet]) -> list[float]:
    """Chance selon les cotes d'atteindre chaque palier (palier 1 : 1)."""
    out, chance = [], 1.0
    for s in steps:
        out.append(chance)
        chance *= 1 / _odds(s, bets)
    return out


def _survival(
    rows: list[tuple[Montante, list[MontanteStep], dict[int, Bet]]],
) -> list[dict[str, Any]]:
    """Par palier : part des montantes terminées qui l'ont atteint, contre l'attendu."""
    finished = [r for r in rows if r[0].status in FINISHED]
    if not finished:
        return []
    depth = max(len(steps) for _, steps, _ in finished)
    out = []
    for k in range(1, depth + 1):
        having = [(m, s, b) for m, s, b in finished if len(s) >= k]
        if not having:
            break
        reached = sum(1 for m, s, _ in having if _reached(m, s) >= k)
        expected = sum(_expected_reach(s, b)[k - 1] for _, s, b in having) / len(having)
        out.append({
            "step": k, "montantes": len(having), "reached": round(reached / len(having), 4),
            "expected": round(expected, 4),
        })  # fmt: skip
    return out


async def _returned(session: AsyncSession, m: Montante) -> int:
    """Ce que la montante a rendu au solde (encaissé, gain final, parts sécurisées)."""
    if m.status == "active":
        return 0
    return int((await plan(session, m))["cashable"])


async def player_summary(session: AsyncSession, user_id: int) -> dict[str, Any]:
    """Bilan et analyse des montantes d'un joueur (M1, M2)."""
    rows = await _load(session, user_id)
    counts = {"completed": 0, "lost": 0, "cashed_out": 0, "active": 0}
    staked = returned = 0
    stops: dict[str, dict[int, int]] = {"lost": defaultdict(int), "cashed_out": defaultdict(int)}
    choices = {
        k: {"steps": 0, "won": 0}
        for k in ("engine", "player", "unknown", "out_of_range")
    }  # fmt: skip
    markets: dict[str, dict[str, int]] = defaultdict(lambda: {"won": 0, "lost": 0})
    out_of_range_cost = 0
    for m, steps, bets in rows:
        counts[m.status] = counts.get(m.status, 0) + 1
        staked += m.start_stake
        returned += await _returned(session, m)
        if m.status in stops:
            stops[m.status][_reached(m, steps)] += 1
        for s in steps:
            if s.result not in (*WON_STEPS, "lost"):
                continue
            won = s.result in WON_STEPS
            origin = {True: "engine", False: "player", None: "unknown"}[s.suggested]
            for key in (origin, *(("out_of_range",) if s.out_of_range else ())):
                choices[key]["steps"] += 1
                choices[key]["won"] += won
            if s.out_of_range and won and m.status == "completed" and s.bet_id in bets:
                # Gain manqué à l'arrivée : cote jouée contre le bas de la plage.
                low = float(s.odds_min)
                played = float(bets[s.bet_id].total_odds)
                if played < low:
                    final = await _returned(session, m)
                    out_of_range_cost += int(final * (low / played - 1))
            if s.bet_id:
                for sel in await session.scalars(
                    select(BetSelection).where(BetSelection.bet_id == s.bet_id)
                ):
                    if sel.result in ("win", "half_win"):
                        markets[sel.market]["won"] += 1
                    elif sel.result in ("loss", "half_loss"):
                        markets[sel.market]["lost"] += 1
    finished = sum(counts[k] for k in FINISHED)
    return {
        "montantes": len(rows),
        "counts": counts,
        "finished": finished,
        "staked": staked,
        "returned": returned,
        "net": returned - staked,
        "survival": _survival(rows),
        "stops": {
            k: [{"step": n, "count": c} for n, c in sorted(v.items())] for k, v in stops.items()
        },
        "choices": choices,
        "out_of_range_cost": out_of_range_cost,
        "markets": sorted(
            ({"market": k, **v} for k, v in markets.items()),
            key=lambda r: -(r["won"] + r["lost"]),
        ),
        "enough": finished >= MIN_FINISHED,
        "min_finished": MIN_FINISHED,
    }


def _band(number: int) -> str:
    return "1-2" if number <= 2 else "3-4" if number <= 4 else "5 et +"


async def reliability(session: AsyncSession) -> dict[str, Any]:
    """Fiabilité des montantes pour tous les joueurs (M4), sans nom."""
    rows = await _load(session)
    bands: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for _, steps, _bets in rows:
        for s in steps:
            if s.result not in (*WON_STEPS, "lost") or not s.bet_id:
                continue
            probs = [
                p.model_probability
                for p in await session.scalars(
                    select(BetSelection).where(BetSelection.bet_id == s.bet_id)
                )
            ]
            if not probs or any(p is None for p in probs):
                continue
            chance = math.prod(p for p in probs if p is not None)
            bands[_band(s.number)].append((chance, 1.0 if s.result in WON_STEPS else 0.0))
    steps_out = []
    for band in ("1-2", "3-4", "5 et +"):
        items = bands.get(band)
        if not items:
            continue
        n = len(items)
        announced = sum(p for p, _ in items) / n
        won = sum(w for _, w in items) / n
        margin = 2 * math.sqrt(sum(p * (1 - p) for p, _ in items)) / n
        steps_out.append({
            "steps": band, "count": n, "announced": round(announced, 4), "won": round(won, 4),
            "fair": abs(won - announced) <= margin,
        })  # fmt: skip
    finished = [r for r in rows if r[0].status in FINISHED]
    to_end = sum(1 for m, _, _ in finished if m.status == "completed")
    expected = (
        sum(math.prod(1 / _odds(s, b) for s in steps) for _, steps, b in finished) / len(finished)
        if finished
        else None
    )
    staked = sum(m.start_stake for m, _, _ in finished)
    returned = sum([await _returned(session, m) for m, _, _ in finished])
    return {
        "steps": steps_out,
        "finished": len(finished),
        "to_end": to_end,
        "to_end_share": round(to_end / len(finished), 4) if finished else None,
        "expected_share": round(expected, 4) if expected is not None else None,
        "staked": staked,
        "returned": returned,
        "yield": round((returned - staked) / staked, 4) if staked else None,
        "enough": len(finished) >= MIN_FINISHED,
        "min_finished": MIN_FINISHED,
    }


async def console_overview(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    """Surveillance des montantes pour la console (M5) : aucune donnée personnelle."""
    now = now or datetime.now(UTC)
    rows = await _load(session)
    month = now - timedelta(days=30)
    recent = [r for r in rows if r[0].status in FINISHED and (r[0].closed_at or now) >= month]
    stops: dict[int, int] = defaultdict(int)
    for m, steps, _ in recent:
        if m.status != "completed":
            stops[_reached(m, steps)] += 1
    expected = (
        sum(math.prod(1 / _odds(s, b) for s in steps) for _, steps, b in recent) / len(recent)
        if recent
        else None
    )
    alerts: list[dict[str, Any]] = []
    # Paliers dont le pari attend son règlement plus de 24 h après le dernier coup d'envoi.
    late = 0
    idle = 0
    for m, steps, bets in rows:
        if m.status != "active":
            continue
        step = next((s for s in steps if s.number == m.current_step), None)
        if step is None:
            continue
        bet = bets.get(step.bet_id) if step.bet_id else None
        if bet is not None and bet.status == "open":
            kickoffs = [
                k
                for k in await session.scalars(
                    select(Match.kickoff_at)
                    .join(BetSelection, BetSelection.match_id == Match.id)
                    .where(BetSelection.bet_id == bet.id)
                )
                if k is not None
            ]
            if kickoffs and now - max(kickoffs) > timedelta(hours=26):
                late += 1
        elif bet is None:
            last = max(
                [m.created_at, *(b.settled_at or b.placed_at for b in bets.values()
                                 if b.montante_step_id in {s.id for s in steps})],
            )  # fmt: skip
            if now - last > timedelta(days=7):
                idle += 1
    if late:
        alerts.append({"level": "warning", "text": f"{late} palier(s) attendent leur règlement "
                       "depuis plus de 24 h après la fin du match"})  # fmt: skip
    if idle:
        alerts.append({"level": "warning", "text": f"{idle} montante(s) sans pari depuis 7 jours"})
    played_month = [
        s for _, steps, bets in rows for s in steps
        if s.bet_id and s.bet_id in bets and bets[s.bet_id].placed_at >= month
    ]  # fmt: skip
    off = sum(1 for s in played_month if s.out_of_range)
    if played_month:
        alerts.append({"level": "info", "text": f"Paliers hors plage sur 30 jours : {off} sur "
                       f"{len(played_month)}"})  # fmt: skip
    losing: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for s in played_month:
        if s.result not in (*WON_STEPS, "lost"):
            continue
        for sel in await session.scalars(
            select(BetSelection).where(BetSelection.bet_id == s.bet_id)
        ):
            losing[sel.market][0] += 1
            losing[sel.market][1] += sel.result in ("loss", "half_loss")
    worst = max(
        ((k, n, lost) for k, (n, lost) in losing.items() if n >= 5),
        key=lambda r: r[2] / r[1],
        default=None,
    )
    if worst is not None:
        alerts.append({"level": "info", "market": worst[0], "text": f"Marché qui perd le plus en "
                       f"montante : {worst[0]} ({worst[2]} perdus sur {worst[1]})"})  # fmt: skip
    return {
        "active": sum(1 for m, _, _ in rows if m.status == "active"),
        "finished_30d": len(recent),
        "to_end_share": (
            round(sum(1 for m, _, _ in recent if m.status == "completed") / len(recent), 4)
            if recent
            else None
        ),
        "expected_share": round(expected, 4) if expected is not None else None,
        "stops": [{"step": k, "count": v} for k, v in sorted(stops.items())],
        "alerts": alerts,
    }
