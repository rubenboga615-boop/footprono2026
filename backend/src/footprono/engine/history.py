"""Historique des matchs en tableaux numpy, chargé depuis la base.

Une ligne par match ; les valeurs absentes sont ``nan``. Seule donnée complétée : les
xG Understat absents, remplacés par ceux d'API-Football remis au niveau Understat
(``fill_api_xg``). Un match sans aucun xG garde ``nan`` et le modèle en tient compte.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.football.referees import referee_key
from footprono.ingestion.reference import AWARDED_MATCHES, NON_LEAGUE_CODES

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
    # Statistiques de match (football-data ; API-Football là où football-data n'a pas de
    # fichier) : nom -> (domicile, extérieur), voir STATS.
    stats: dict[str, tuple[FloatArray, FloatArray]] = field(default_factory=dict)
    # Arbitre : API-Football si connu (même écriture partout), sinon football-data.
    referee: NDArray[np.str_] = field(default_factory=lambda: np.array([], dtype=np.str_))
    # Passes dangereuses (« deep », Understat) : vides si non chargées.
    hdeep: FloatArray = field(default_factory=lambda: np.array([], dtype=np.float64))
    adeep: FloatArray = field(default_factory=lambda: np.array([], dtype=np.float64))
    # Matchs dont les xG Understat absents ont été remplacés par ceux d'API-Football.
    api_xg_filled: int = 0

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
            hdeep=self.hdeep[mask] if len(self.hdeep) else self.hdeep,
            adeep=self.adeep[mask] if len(self.adeep) else self.adeep,
        )  # fmt: skip


_MATCHES = text(
    """
    SELECT m.id, c.code, s.start_year, m.match_date, m.home_team_id, m.away_team_id,
           m.status::text, m.home_goals, m.away_goals, m.home_goals_ht, m.away_goals_ht,
           h.name, a.name,
           xh.xg AS hxg, xa.xg AS axg,
           CASE WHEN src.api THEN sh.corners ELSE m.home_corners END,
           CASE WHEN src.api THEN sa.corners ELSE m.away_corners END,
           CASE WHEN src.api THEN sh.yellow_cards ELSE m.home_yellow_cards END,
           CASE WHEN src.api THEN sa.yellow_cards ELSE m.away_yellow_cards END,
           CASE WHEN src.api THEN sh.red_cards ELSE m.home_red_cards END,
           CASE WHEN src.api THEN sa.red_cards ELSE m.away_red_cards END,
           CASE WHEN src.api THEN sh.total_shots ELSE m.home_shots END,
           CASE WHEN src.api THEN sa.total_shots ELSE m.away_shots END,
           CASE WHEN src.api THEN sh.shots_on_goal ELSE m.home_shots_on_target END,
           CASE WHEN src.api THEN sa.shots_on_goal ELSE m.away_shots_on_target END,
           CASE WHEN src.api THEN sh.fouls ELSE m.home_fouls END,
           CASE WHEN src.api THEN sa.fouls ELSE m.away_fouls END,
           m.api_referee, m.referee, xh.deep AS hdeep, xa.deep AS adeep, m.api_status,
           sh.expected_goals, sa.expected_goals
    FROM matches m
    JOIN seasons s ON s.id = m.season_id
    JOIN competitions c ON c.id = s.competition_id
    CROSS JOIN LATERAL (SELECT c.football_data_division IS NULL AS api) src
    JOIN teams h ON h.id = m.home_team_id
    JOIN teams a ON a.id = m.away_team_id
    LEFT JOIN match_advanced_stats xh ON xh.match_id = m.id AND xh.team_id = m.home_team_id
        AND xh.source = 'understat'
    LEFT JOIN match_advanced_stats xa ON xa.match_id = m.id AND xa.team_id = m.away_team_id
        AND xa.source = 'understat'
    -- Championnats sans football-data : statistiques de match d'API-Football (match entier).
    LEFT JOIN match_team_stats sh ON sh.match_id = m.id AND sh.team_id = m.home_team_id
        AND sh.source = 'api_football' AND sh.period = 'full'
    LEFT JOIN match_team_stats sa ON sa.match_id = m.id AND sa.team_id = m.away_team_id
        AND sa.source = 'api_football' AND sa.period = 'full'
    -- Coupes d'Europe : moteur à part (engine/cups.py), jamais dans les modèles des
    -- championnats.
    WHERE c.code <> ALL(CAST(:cups AS text[]))
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
    rows = (await session.execute(_MATCHES, {"cups": list(NON_LEAGUE_CODES)})).all()
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
            # Annulé, ou donné sur tapis vert (liste connue, ou « AWD » chez API-Football).
            [
                r[6] == "cancelled"
                or r[31] == "AWD"
                or (r[1], r[2], r[11], r[12]) in AWARDED_MATCHES
                for r in rows
            ],
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
        # Un arbitre = une clé (initiale + nom), quelle que soit l'orthographe de la
        # source : « Stuart Attwell », « S. Attwell » et « S Attwell » ne font qu'un
        # (meilleur sur 2019-21 comme sur 2022-26, docs/MOTEUR.md).
        referee=np.array(
            [referee_key(r[27] or r[28]) if (r[27] or r[28]) else "" for r in rows],
            dtype=np.str_,
        ),
        hdeep=np.array([_nan(r[29]) for r in rows]),
        adeep=np.array([_nan(r[30]) for r in rows]),
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
    hist.api_xg_filled = fill_api_xg(
        hist, np.array([_nan(r[32]) for r in rows]), np.array([_nan(r[33]) for r in rows])
    )
    # Championnats de niveau 2 : xG « maison » tirés des tirs (engine/tiers.py).
    from footprono.engine.tiers import apply_shot_xg

    apply_shot_xg(hist)
    return hist


# Remplacement des xG Understat absents (site en panne depuis le 20 septembre 2026) :
# rapport Understat / API-Football sur les matchs qui ont les deux, dans l'année qui
# précède chaque match, et au moins API_XG_MIN_MATCHES matchs pour l'estimer.
API_XG_WINDOW_DAYS = 365
API_XG_MIN_MATCHES = 100


def fill_api_xg(hist: History, api_h: FloatArray, api_a: FloatArray) -> int:
    """Complète sur place les xG Understat absents avec ceux d'API-Football.

    Les xG d'API-Football suivent ceux d'Understat (corrélation 0,94) mais sont plus bas
    (1,40 contre 1,52 par équipe et par match) : multipliés, championnat par championnat,
    par le rapport des deux sur l'année précédente (calculé avant le match : jamais de
    données futures). Panne simulée sur 2023-2025 (docs/MOTEUR.md) : meilleur que les
    buts seuls sur chaque saison et chaque marché, presque au niveau d'Understat.
    Les passes dangereuses (« deep ») restent absentes. Renvoie le nombre de matchs complétés.
    """
    filled = 0
    has_api = ~np.isnan(api_h) & ~np.isnan(api_a)
    has_us = ~np.isnan(hist.hxg) & ~np.isnan(hist.axg)
    for comp in np.unique(hist.competition):
        c = hist.competition == comp
        both = np.where(c & has_us & has_api)[0]
        todo = np.where(c & ~has_us & has_api)[0]
        if not len(both) or not len(todo):
            continue
        days = hist.date[both]  # l'historique est trié par date
        us_sum = np.concatenate([[0.0], np.cumsum(hist.hxg[both] + hist.axg[both])])
        api_sum = np.concatenate([[0.0], np.cumsum(api_h[both] + api_a[both])])
        end = np.searchsorted(days, hist.date[todo], side="left")
        start = np.searchsorted(
            days, hist.date[todo] - np.timedelta64(API_XG_WINDOW_DAYS, "D"), side="left"
        )
        for i, lo, hi in zip(todo, start, end, strict=True):
            if hi - lo < API_XG_MIN_MATCHES:
                continue
            k = (us_sum[hi] - us_sum[lo]) / max(api_sum[hi] - api_sum[lo], 1e-9)
            hist.hxg[i], hist.axg[i] = k * api_h[i], k * api_a[i]
            filled += 1
    return filled


def season_start(start_year: int) -> np.datetime64:
    return np.datetime64(date(start_year, 7, 1), "D")
