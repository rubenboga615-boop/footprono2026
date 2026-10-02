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

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker.models import Bet, BetSelection
from footprono.football.models import Competition, Match, Season

MIN_BAND = 20
BANDS = ((0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01))
RISING_FACTOR = 2.0  # mises de la semaine au moins doublées : rappel de jeu responsable

_WON = {"win", "half_win"}
_LOST = {"loss", "half_loss"}


def _rate(won: int, lost: int) -> float | None:
    return None if won + lost == 0 else round(won / (won + lost), 4)


def _group(rows: list[tuple[str, str]]) -> list[dict[str, Any]]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for key, result in rows:
        c = counts[key]
        c[0 if result in _WON else 1 if result in _LOST else 2] += 1
    out = [
        {"key": k, "won": w, "lost": lo, "push": p, "rate": _rate(w, lo)}
        for k, (w, lo, p) in counts.items()
    ]
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
        "by_market": _group([(s.market, s.result) for s, _ in graded]),
        "by_competition": _group([(code, s.result) for s, code in graded]),
        "calibration": bands,
        "min_band": MIN_BAND,
        "stakes_7d": stakes_7d,
        "stakes_prev_7d": stakes_prev,
        "rising": stakes_prev > 0 and stakes_7d >= RISING_FACTOR * stakes_prev,
    }
