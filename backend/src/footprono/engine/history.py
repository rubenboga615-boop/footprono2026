"""Historique des matchs en tableaux numpy, chargé depuis la base.

Une ligne par match ; les valeurs absentes sont ``nan``. Aucune donnée n'est
complétée : un match sans xG garde ``nan`` et le modèle en tient compte.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.ingestion.reference import AWARDED_MATCHES

# Ordre de préférence des bookmakers pour la référence « marché ».
MARKET_BOOKMAKERS = ("PS", "Avg", "BbAv", "B365")

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass
class History:
    match_id: IntArray
    competition: NDArray[np.str_]
    season: IntArray
    date: NDArray[np.datetime64]
    home: IntArray
    away: IntArray
    finished: NDArray[np.bool_]
    excluded: NDArray[np.bool_]  # matchs sur tapis vert ou annulés
    hg: FloatArray
    ag: FloatArray
    hht: FloatArray
    aht: FloatArray
    hxg: FloatArray
    axg: FloatArray
    # Cotes de référence (préférence MARKET_BOOKMAKERS), ``nan`` si absentes.
    odds: dict[str, FloatArray] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.match_id)

    def subset(self, mask: NDArray[np.bool_]) -> "History":
        return History(
            **{
                name: getattr(self, name)[mask]
                for name in (
                    "match_id", "competition", "season", "date", "home", "away", "finished",
                    "excluded", "hg", "ag", "hht", "aht", "hxg", "axg",
                )
            },
            odds={k: v[mask] for k, v in self.odds.items()},
        )  # fmt: skip


_MATCHES = text(
    """
    SELECT m.id, c.code, s.start_year, m.match_date, m.home_team_id, m.away_team_id,
           m.status::text, m.home_goals, m.away_goals, m.home_goals_ht, m.away_goals_ht,
           h.name, a.name,
           xh.xg AS hxg, xa.xg AS axg
    FROM matches m
    JOIN seasons s ON s.id = m.season_id
    JOIN competitions c ON c.id = s.competition_id
    JOIN teams h ON h.id = m.home_team_id
    JOIN teams a ON a.id = m.away_team_id
    LEFT JOIN match_advanced_stats xh ON xh.match_id = m.id AND xh.team_id = m.home_team_id
        AND xh.source = 'understat'
    LEFT JOIN match_advanced_stats xa ON xa.match_id = m.id AND xa.team_id = m.away_team_id
        AND xa.source = 'understat'
    ORDER BY m.match_date, m.id
    """
)

_ODDS = text(
    """
    SELECT match_id, bookmaker, market, line, timing::text, selection, price
    FROM match_odds
    WHERE bookmaker = ANY(:books) AND (market = '1X2' OR (market = 'OU' AND line = 2.5))
    """
)

_ODDS_SLOTS = {
    ("1X2", "home"): ("1x2", 0), ("1X2", "draw"): ("1x2", 1), ("1X2", "away"): ("1x2", 2),
    ("OU", "over"): ("ou25", 0), ("OU", "under"): ("ou25", 1),
}  # fmt: skip


def _nan(value: object) -> float:
    return float("nan") if value is None else float(value)  # type: ignore[arg-type]


async def load_history(session: AsyncSession) -> History:
    rows = (await session.execute(_MATCHES)).all()
    n = len(rows)
    ids = np.array([r[0] for r in rows], dtype=np.int64)
    hist = History(
        match_id=ids,
        competition=np.array([r[1] for r in rows], dtype=np.str_),
        season=np.array([r[2] for r in rows], dtype=np.int64),
        date=np.array([np.datetime64(r[3], "D") for r in rows], dtype="datetime64[D]"),
        home=np.array([r[4] for r in rows], dtype=np.int64),
        away=np.array([r[5] for r in rows], dtype=np.int64),
        finished=np.array([r[6] == "finished" for r in rows], dtype=bool),
        excluded=np.array(
            [r[6] == "cancelled" or (r[1], r[2], r[11], r[12]) in AWARDED_MATCHES for r in rows],
            dtype=bool,
        ),
        hg=np.array([_nan(r[7]) for r in rows]),
        ag=np.array([_nan(r[8]) for r in rows]),
        hht=np.array([_nan(r[9]) for r in rows]),
        aht=np.array([_nan(r[10]) for r in rows]),
        hxg=np.array([_nan(r[13]) for r in rows]),
        axg=np.array([_nan(r[14]) for r in rows]),
    )
    index = {int(mid): i for i, mid in enumerate(ids)}
    widths = {"1x2": 3, "ou25": 2}
    for timing in ("pre", "close"):
        for key, width in widths.items():
            hist.odds[f"{timing}_{key}"] = np.full((n, width), np.nan)
    # Un même bookmaker pour toutes les issues d'un marché (jamais de mélange),
    # le premier de MARKET_BOOKMAKERS qui les cote toutes.
    quotes: dict[tuple[int, str, str], dict[str, dict[int, float]]] = {}
    for mid, book, market, _line, timing, selection, price in (
        await session.execute(_ODDS, {"books": list(MARKET_BOOKMAKERS)})
    ).all():
        slot = _ODDS_SLOTS.get((market, selection))
        i = index.get(int(mid))
        if slot is None or i is None:
            continue
        key, col = slot
        quotes.setdefault((i, timing, key), {}).setdefault(book, {})[col] = float(price)
    for (i, timing, key), books in quotes.items():
        for book in MARKET_BOOKMAKERS:
            prices = books.get(book, {})
            if len(prices) == widths[key]:
                for col, price in prices.items():
                    hist.odds[f"{timing}_{key}"][i, col] = price
                break
    return hist


def season_start(start_year: int) -> np.datetime64:
    return np.datetime64(date(start_year, 7, 1), "D")
