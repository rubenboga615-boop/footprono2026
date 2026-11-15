"""Comparaison des moteurs (maquette K6 validée le 15/11/2026) : le juge entre le moteur 1
(inchangé) et le moteur 2 (calé sur la cote de référence).

- Chances : avant chaque match, les chances 1-N-2 des deux moteurs sont relevées (la
  dernière avant le coup d'envoi compte) ; après le match, log loss de chacun sur les
  **mêmes** matchs (plus bas = plus juste).
- Argent : chaque proposition de chaque moteur est enregistrée, jouée ou non (Coupon
  intelligent et suggestions de palier en mode comparaison ; coupons du jour des deux
  moteurs), puis réglée avec les règles des paris. Bilan avec une mise fixe de 1 000 F sur
  chaque proposition.
- Verdict seulement avec assez de données : au moins 300 matchs comparés et 200 propositions
  réglées par moteur. Jamais de conclusion inventée avant.
"""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker import service, settlement
from footprono.bookmaker.models import BetSelection
from footprono.bookmaker.smart_models import EngineMatchChances, EngineProposal, SmartCoupon
from footprono.football.models import Match, MatchStatus

STAKE = 1000  # F, mise fixe de chaque proposition (bilan en argent)
MIN_MATCHES = 300
MIN_PROPOSALS = 200
# Chances relevées pour les matchs qui commencent dans les prochaines heures (relevé toutes
# les 10 minutes : la dernière avant le coup d'envoi reste).
CHANCES_AHEAD = timedelta(hours=3)
OUTCOMES = ("home", "draw", "away")
SOURCES = {
    "coupon": "Coupon intelligent",
    "daily": "Coupons du jour",
    "montante": "Montante (paliers)",
}
_EPS = 1e-6


def _key(day: str, selections: Sequence[dict[str, Any]]) -> str:
    parts = sorted(
        f"{s['match_id']}:{s['market']}:{s.get('line') or ''}:{s['selection']}" for s in selections
    )
    return f"{day}|{','.join(parts)}"[:400]


async def record_proposals(
    session: AsyncSession,
    engine: int,
    source: str,
    proposals: Sequence[dict[str, Any]],
    now: datetime | None = None,
) -> int:
    """Enregistre des propositions (``selections``, ``total_odds``, probabilité) d'un moteur ;
    la même proposition le même jour ne compte qu'une fois. Renvoie le nombre de nouvelles."""
    now = now or datetime.now(UTC)
    rows = []
    for p in proposals:
        sels = p.get("selections") or []
        if not sels:
            continue
        rows.append(
            {
                "engine": engine,
                "source": source,
                "key": _key(now.date().isoformat(), sels),
                "selections": [
                    {
                        "match_id": s["match_id"],
                        "market": s["market"],
                        "line": s.get("line") or "",
                        "selection": s["selection"],
                        "odds": str(s["odds"]),
                        "model_probability": s.get("model_probability"),
                        "result": "pending",
                    }
                    for s in sels
                ],
                "total_odds": Decimal(str(p["total_odds"])),
                "probability": float(p.get("probability", p.get("model_probability", 0.0))),
                "proposed_at": now,
                "status": "pending",
            }
        )
    if not rows:
        return 0
    result = await session.execute(
        insert(EngineProposal)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["engine", "source", "key"])
        .returning(EngineProposal.id)
    )
    return len(result.all())


async def settle_proposals(session: AsyncSession, now: datetime | None = None) -> int:
    """Règle les propositions dont tous les matchs sont connus (perdue dès une sélection
    perdue), avec les règles des paris ; gain pour une mise de ``STAKE``."""
    now = now or datetime.now(UTC)
    done = 0
    pending = await session.scalars(
        select(EngineProposal).where(EngineProposal.status == "pending")
    )
    for p in pending.all():
        grades, selections = [], []
        for s in p.selections:
            probe = BetSelection(
                match_id=s["match_id"],
                market=s["market"],
                line=s["line"],
                selection=s["selection"],
                odds=Decimal(s["odds"]),
            )
            grade = await settlement.grade_selection(session, probe, now)
            selections.append({**s, "result": grade.result if grade else "pending"})
            if grade is not None:
                grades.append(grade)
        p.selections = selections
        if any(g.result == "loss" for g in grades) or len(grades) == len(selections):
            outcome, payout = settlement.bet_outcome(STAKE, grades)
            p.status = "void" if outcome == "push" else outcome
            p.payout = payout
            p.settled_at = now
            done += 1
    await session.commit()
    return done


def _one_x_two(probs: dict[str, float]) -> dict[str, float] | None:
    out = {o: probs.get(f"1X2||{o}") for o in OUTCOMES}
    if any(v is None for v in out.values()):
        return None
    return {o: round(float(v), 5) for o, v in out.items() if v is not None}


async def record_chances(session: AsyncSession, now: datetime | None = None) -> int:
    """Chances 1-N-2 des deux moteurs pour les matchs des prochaines heures (remplacées à
    chaque relevé jusqu'au coup d'envoi)."""
    now = now or datetime.now(UTC)
    ids = list(
        await session.scalars(
            select(Match.id).where(
                Match.status == MatchStatus.SCHEDULED,
                Match.kickoff_at > now,
                Match.kickoff_at <= now + CHANCES_AHEAD,
            )
        )
    )
    if not ids:
        return 0
    one = await service.models_probabilities(session, ids)
    two = await service.engine2_probabilities(session, ids, now)
    rows = []
    for m in ids:
        e1, e2 = _one_x_two(one.get(m, {})), _one_x_two(two.get(m, {}))
        if e1 is None or e2 is None:
            continue
        calibrated = service.CALIBRATED_KEY in two.get(m, {})
        rows.append(
            {"match_id": m, "engine1": e1, "engine2": e2, "calibrated": calibrated,
             "recorded_at": now}
        )  # fmt: skip
    if not rows:
        return 0
    stmt = insert(EngineMatchChances).values(rows)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["match_id"],
            set_={
                "engine1": stmt.excluded.engine1,
                "engine2": stmt.excluded.engine2,
                "calibrated": stmt.excluded.calibrated,
                "recorded_at": stmt.excluded.recorded_at,
            },
        )
    )
    await session.commit()
    return len(rows)


def _outcome(home: int, away: int) -> str:
    return "home" if home > away else "away" if away > home else "draw"


# Multiplicateur de la mise selon le résultat d'une sélection (mêmes règles que les paris).
def _factor(result: str, odds: Decimal) -> Decimal:
    return {
        "win": odds,
        "half_win": (1 + odds) / 2,
        "push": Decimal(1),
        "half_loss": Decimal("0.5"),
    }.get(result, Decimal(0))


def _daily_payout(coupon: SmartCoupon) -> int:
    """Gain d'un coupon du jour réglé pour une mise de ``STAKE`` (résultat de chaque ligne)."""
    factor = Decimal(1)
    for sel in coupon.selections:
        factor *= _factor(sel.get("result", "loss"), Decimal(str(sel["odds"])))
    return math.floor(STAKE * factor)


def _money(rows: Sequence[tuple[str, int | None]]) -> dict[str, Any]:
    """Bilan à mise fixe : (statut, gain) des propositions réglées (remboursées exclues)."""
    done = [(s, pay or 0) for s, pay in rows if s in ("won", "lost", "partial")]
    n = len(done)
    profit = sum(pay for _, pay in done) - n * STAKE
    return {
        "settled": n,
        "won": sum(s == "won" for s, _ in done),
        "profit": profit,
        "yield": round(profit / (n * STAKE), 4) if n else None,
    }


async def comparison(session: AsyncSession) -> dict[str, Any]:
    """Moteur 1 contre moteur 2 : log loss sur les mêmes matchs, bilan en argent par source,
    et le verdict seulement s'il y a assez de données."""
    rows = (
        await session.execute(
            select(EngineMatchChances, Match.home_goals, Match.away_goals)
            .join(Match, Match.id == EngineMatchChances.match_id)
            .where(
                Match.status == MatchStatus.FINISHED,
                Match.home_goals.is_not(None),
                Match.away_goals.is_not(None),
                # Relevé avant le coup d'envoi seulement.
                EngineMatchChances.recorded_at <= Match.kickoff_at,
            )
        )
    ).all()
    loss = {1: 0.0, 2: 0.0}
    calibrated = 0
    for chances, hg, ag in rows:
        result = _outcome(hg, ag)
        loss[1] -= math.log(max(chances.engine1.get(result, 0.0), _EPS))
        loss[2] -= math.log(max(chances.engine2.get(result, 0.0), _EPS))
        calibrated += chances.calibrated
    n = len(rows)

    money: dict[str, dict[int, dict[str, Any]]] = {}
    proposals = (
        await session.execute(
            select(EngineProposal.source, EngineProposal.engine, EngineProposal.status,
                   EngineProposal.payout)
        )
    ).all()  # fmt: skip
    for source in ("coupon", "montante"):
        money[source] = {
            e: _money([(s, pay) for src, eng, s, pay in proposals if src == source and eng == e])
            for e in (1, 2)
        }
    # Coupons du jour : depuis le premier jour où le moteur 2 a les siens (mêmes jours).
    first = await session.scalar(
        select(SmartCoupon.day).where(SmartCoupon.engine == 2).order_by(SmartCoupon.day).limit(1)
    )
    daily: dict[int, list[tuple[str, int | None]]] = {1: [], 2: []}
    if first is not None:
        coupons = (await session.scalars(select(SmartCoupon).where(SmartCoupon.day >= first))).all()
        for c in coupons:
            if c.engine in daily and c.status != "pending":
                daily[c.engine].append((c.status, _daily_payout(c)))
    money["daily"] = {e: _money(daily[e]) for e in (1, 2)}

    settled = {e: sum(money[s][e]["settled"] for s in money) for e in (1, 2)}
    enough = n >= MIN_MATCHES and min(settled.values()) >= MIN_PROPOSALS
    return {
        "matches": n,
        "calibrated": calibrated,
        "log_loss": {str(e): round(loss[e] / n, 4) if n else None for e in (1, 2)},
        "money": [
            {"source": s, "label": SOURCES[s], "engines": {str(e): money[s][e] for e in (1, 2)}}
            for s in ("coupon", "daily", "montante")
        ],
        "settled": {str(e): v for e, v in settled.items()},
        "stake": STAKE,
        "enough": enough,
        "min_matches": MIN_MATCHES,
        "min_proposals": MIN_PROPOSALS,
    }
