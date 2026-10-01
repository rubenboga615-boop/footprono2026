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

# Statistiques de match : colonne (domicile) de la requête, extérieur = suivante.
STATS = {
    "corners": 15, "yellow_cards": 17, "red_cards": 19, "shots": 21,
    "shots_on_target": 23, "fouls": 25,
}  # fmt: skip

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
    # Statistiques de match (football-data) : nom -> (domicile, extérieur), voir STATS.
    stats: dict[str, tuple[FloatArray, FloatArray]] = field(default_factory=dict)
    # Arbitre : API-Football si connu (même écriture partout), sinon football-data.
    referee: NDArray[np.str_] = field(default_factory=lambda: np.array([], dtype=np.str_))

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
            stats={k: (h[mask], a[mask]) for k, (h, a) in self.stats.items()},
            referee=self.referee[mask] if len(self.referee) else self.referee,
        )  # fmt: skip


_MATCHES = text(
    """
    SELECT m.id, c.code, s.start_year, m.match_date, m.home_team_id, m.away_team_id,
           m.status::text, m.home_goals, m.away_goals, m.home_goals_ht, m.away_goals_ht,
           h.name, a.name,
           xh.xg AS hxg, xa.xg AS axg,
           m.home_corners, m.away_corners, m.home_yellow_cards, m.away_yellow_cards,
           m.home_red_cards, m.away_red_cards, m.home_shots, m.away_shots,
           m.home_shots_on_target, m.away_shots_on_target, m.home_fouls, m.away_fouls,
           m.api_referee, m.referee
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
    WHERE bookmaker = ANY(:books)
      AND (market IN ('1X2', 'AH') OR (market = 'OU' AND line = 2.5))
    """
)

_ODDS_SLOTS = {
    ("1X2", "home"): ("1x2", 0), ("1X2", "draw"): ("1x2", 1), ("1X2", "away"): ("1x2", 2),
    ("OU", "over"): ("ou25", 0), ("OU", "under"): ("ou25", 1),
    # Handicap asiatique : colonne 0 = ligne (vue du domicile), 1-2 = cotes.
    ("AH", "home"): ("ah", 1), ("AH", "away"): ("ah", 2),
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
        stats={
            name: (
                np.array([_nan(r[col]) for r in rows]),
                np.array([_nan(r[col + 1]) for r in rows]),
            )
            for name, col in STATS.items()
        },
        referee=np.array(
            [f"api:{r[27]}" if r[27] else (f"fd:{r[28]}" if r[28] else "") for r in rows],
            dtype=np.str_,
        ),
    )
    index = {int(mid): i for i, mid in enumerate(ids)}
    widths = {"1x2": 3, "ou25": 2, "ah": 3}
    for timing in ("pre", "close"):
        for key, width in widths.items():
            hist.odds[f"{timing}_{key}"] = np.full((n, width), np.nan)
    # Un même bookmaker pour toutes les issues d'un marché (jamais de mélange),
    # le premier de MARKET_BOOKMAKERS qui les cote toutes.
    quotes: dict[tuple[int, str, str], dict[str, dict[int, float]]] = {}
    lines: dict[tuple[int, str, str], set[float]] = {}
    for mid, book, market, line, timing, selection, price in (
        await session.execute(_ODDS, {"books": list(MARKET_BOOKMAKERS)})
    ).all():
        slot = _ODDS_SLOTS.get((market, selection))
        i = index.get(int(mid))
        if slot is None or i is None:
            continue
        key, col = slot
        quotes.setdefault((i, timing, key), {}).setdefault(book, {})[col] = float(price)
        if key == "ah":
            lines.setdefault((i, timing, book), set()).add(float(line))
    for (i, timing, key), books in quotes.items():
        for book in MARKET_BOOKMAKERS:
            prices = dict(books.get(book, {}))
            if key == "ah":
                # Les deux côtés cotés sur une seule et même ligne, sinon ignoré.
                book_lines = lines.get((i, timing, book), set())
                if len(prices) != 2 or len(book_lines) != 1:
                    continue
                prices[0] = next(iter(book_lines))
            if len(prices) == widths[key]:
                for col, price in prices.items():
                    hist.odds[f"{timing}_{key}"][i, col] = price
                break
    return hist


def season_start(start_year: int) -> np.datetime64:
    return np.datetime64(date(start_year, 7, 1), "D")
