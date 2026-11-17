"""« Mon bilan » : les paris fictifs réglés d'un joueur, à lui seul.

- Rendement : mises, gains, résultat net, sur les paris réglés (annulés exclus).
- Réussite par marché et par championnat, sélection par sélection (une sélection
  d'un combiné compte pour elle-même) : gagnée (dont demi-gain) contre perdue
  (dont demi-perte) ; remboursées à part.
- Annoncé contre réalisé : sélections groupées par probabilité du moteur au
  moment du pari, à côté de la probabilité selon la cote (1 / cote) et de la
  réussite réelle. Sous ``MIN_BAND`` sélections, la tranche est signalée « peu
  de paris » : l'écart y relève surtout du hasard.
- Jeu responsable : mises des 7 derniers jours contre les 7 précédents.
"""

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker.models import Bet, BetSelection
from footprono.football.models import Competition, Match, Season

MIN_BAND = 20
BANDS = ((0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01))
RISING_FACTOR = 2.0
# Tranches de cote totale des paris (« Mon bilan par cote de coupon »).
ODDS_BANDS = (
    (1.0, 2.0),
    (2.0, 5.0),
    (5.0, 20.0),
    (20.0, float("inf")),
)  # mises de la semaine au moins doublées : rappel de jeu responsable

_WON = {"win", "half_win"}
_LOST = {"loss", "half_loss"}


def _rate(won: int, lost: int) -> float | None:
    return None if won + lost == 0 else round(won / (won + lost), 4)


def _gap(announced: float, won: int, n: int) -> str | None:
    """« low » / « high » : réalisé nettement sous / au-dessus de l'annoncé (plus de deux
    écarts-types du hasard, au moins MIN_BAND sélections) ; None sinon."""
    if n < MIN_BAND:
        return None
    spread = 2 * math.sqrt(max(announced * (1 - announced), 1e-9) / n)
    observed = won / n
    if observed < announced - spread:
        return "low"
    if observed > announced + spread:
        return "high"
    return None


def _group(rows: list[tuple[str, str, float | None]]) -> list[dict[str, Any]]:
    """Par marché ou par championnat. « announced » (maquette du 17/11/2026) : chance moyenne
    donnée par le moteur aux sélections gagnées ou perdues qui en ont une."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    probs: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for key, result, prob in rows:
        c = counts[key]
        c[0 if result in _WON else 1 if result in _LOST else 2] += 1
        if prob is not None and result in _WON | _LOST:
            probs[key].append((prob, result in _WON))
    out = []
    for k, (w, lo, p) in counts.items():
        graded = probs.get(k, [])
        announced = sum(x for x, _ in graded) / len(graded) if graded else None
        out.append(
            {
                "key": k, "won": w, "lost": lo, "push": p, "rate": _rate(w, lo),
                "announced": None if announced is None else round(announced, 4),
                "gap": None if announced is None
                else _gap(announced, sum(1 for _, won in graded if won), len(graded)),
            }
        )  # fmt: skip
    return sorted(out, key=lambda x: -(x["won"] + x["lost"] + x["push"]))


async def player_record(
    session: AsyncSession, user_id: int, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    bets = (await session.scalars(select(Bet).where(Bet.user_id == user_id))).all()
    settled = [b for b in bets if b.status == "settled"]
    staked = sum(b.stake for b in settled)
    returned = sum(b.payout or 0 for b in settled)
    outcomes: defaultdict[str, int] = defaultdict(int)
    for b in settled:
        outcomes[b.outcome or "lost"] += 1

    week = now - timedelta(days=7)
    stakes_7d = sum(b.stake for b in bets if b.placed_at >= week)
    stakes_prev = sum(b.stake for b in bets if week - timedelta(days=7) <= b.placed_at < week)

    rows = (
        await session.execute(
            select(BetSelection, Competition.code)
            .join(Bet, Bet.id == BetSelection.bet_id)
            .join(Match, Match.id == BetSelection.match_id)
            .join(Season, Season.id == Match.season_id)
            .join(Competition, Competition.id == Season.competition_id)
            .where(Bet.user_id == user_id, Bet.status == "settled")
        )
    ).all()
    graded = [(s, code) for s, code in rows if s.result != "pending"]

    bands = []
    for low, high in BANDS:
        sels = [
            s
            for s, _ in graded
            if s.model_probability is not None
            and low <= s.model_probability < high
            and s.result in _WON | _LOST
        ]
        if not sels:
            continue
        won = sum(1 for s in sels if s.result in _WON)
        bands.append(
            {
                "low": low,
                "high": min(high, 1.0),
                "selections": len(sels),
                "announced": round(sum(s.model_probability or 0 for s in sels) / len(sels), 4),
                "implied": round(sum(1 / float(s.odds) for s in sels) / len(sels), 4),
                "observed": round(won / len(sels), 4),
                "enough": len(sels) >= MIN_BAND,
            }
        )

    return {
        "bets": {
            "settled": len(settled),
            "open": sum(1 for b in bets if b.status == "open"),
            "won": outcomes["won"],
            "lost": outcomes["lost"],
            "push": outcomes["push"],
            "partial": outcomes["partial"],
        },
        "staked": staked,
        "returned": returned,
        "profit": returned - staked,
        "yield": None if staked == 0 else round((returned - staked) / staked, 4),
        "by_market": _group([(s.market, s.result, s.model_probability) for s, _ in graded]),
        "by_competition": _group([(c, s.result, s.model_probability) for s, c in graded]),
        "calibration": bands,
        "min_band": MIN_BAND,
        "stakes_7d": stakes_7d,
        "stakes_prev_7d": stakes_prev,
        "rising": stakes_prev > 0 and stakes_7d >= RISING_FACTOR * stakes_prev,
        "by_odds": _by_odds(settled, [s for s, _ in rows]),
    }


def _by_odds(settled: list[Bet], selections: list[BetSelection]) -> list[dict[str, Any]]:
    """Paris réglés par tranche de cote totale : gagnés, chances annoncées, résultat net.

    « Annoncé » : moyenne, sur les paris de la tranche, du produit des probabilités du
    moteur de leurs sélections (paris dont une sélection n'en a pas : non comptés).
    """
    probs: dict[int, list[float | None]] = defaultdict(list)
    for s in selections:
        probs[s.bet_id].append(s.model_probability)
    out = []
    for low, high in ODDS_BANDS:
        bets = [b for b in settled if low <= float(b.total_odds) < high]
        if not bets:
            continue
        announced = [
            math.prod(p)  # type: ignore[arg-type]
            for b in bets
            if (p := probs.get(b.id)) and None not in p
        ]
        out.append(
            {
                "low": low,
                "high": None if math.isinf(high) else high,
                "bets": len(bets),
                "won": sum(1 for b in bets if b.outcome == "won"),
                "announced": round(sum(announced) / len(announced), 4) if announced else None,
                "profit": sum((b.payout or 0) - b.stake for b in bets),
            }
        )
    return out
