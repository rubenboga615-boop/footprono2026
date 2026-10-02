"""Fiche arbitre : cartons par match comparés à la moyenne du championnat (faits seulement).

Noms : selon la source et la saison, un même arbitre s'écrit « Stuart Attwell »,
« S. Attwell » (API-Football) ou « S Attwell » (football-data, Premier League
seulement). Il est reconnu par sa clé initiale + nom (« s attwell ») et affiché
sous sa forme la plus complète.

Comparaison honnête : la moyenne de référence est celle du même championnat sur
les mêmes saisons, pondérée par le nombre de matchs dirigés dans chacune. Sous
``MIN_MATCHES`` matchs, l'écart n'est pas interprété (« pas assez de matchs »).
"""

import unicodedata
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.core.errors import NotFoundError

MIN_MATCHES = 15
RECENT_MATCHES = 5

_ROWS = text(
    """
    select m.id, c.code, s.start_year, m.match_date, h.name as home, a.name as away,
           m.referee, m.api_referee, m.home_yellow_cards as hy, m.away_yellow_cards as ay,
           m.home_red_cards as hr, m.away_red_cards as ar
    from matches m
    join seasons s on s.id = m.season_id
    join competitions c on c.id = s.competition_id
    join teams h on h.id = m.home_team_id
    join teams a on a.id = m.away_team_id
    where m.status = 'finished'
      and m.home_yellow_cards is not null and m.away_yellow_cards is not null
    order by m.match_date, m.id
    """
)


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def referee_key(name: str) -> str:
    """« Stuart Attwell », « S. Attwell », « S Attwell » → « s attwell »."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    parts = plain.replace(".", " ").lower().split()
    if len(parts) < 2:
        return " ".join(parts)
    return f"{parts[0][0]} {' '.join(parts[1:])}"


class _Data:
    """Matchs terminés avec cartons, arbitre ramené à une clé unique."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        forms: dict[str, Counter[str]] = defaultdict(Counter)
        self.keys: list[str | None] = []
        for r in rows:
            name = r.api_referee or r.referee
            key = referee_key(name) if name else None
            self.keys.append(key or None)
            if key:
                forms[key][name] += 1
        # Forme affichée : prénom complet si une source le donne, sinon la plus fréquente.
        self.display = {
            key: max(c, key=lambda f: (len(f.replace(".", " ").split()[0]), c[f]))
            for key, c in forms.items()
        }
        # Moyenne du championnat par saison (tous les matchs avec cartons).
        totals: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
        for r in rows:
            t = totals[(r.code, r.start_year)]
            t[0] += 1
            t[1] += r.hy + r.ay
            t[2] += (r.hr or 0) + (r.ar or 0)
        self.league = {k: (int(n), y / n, red / n) for k, (n, y, red) in totals.items()}

    def by_key(self, key: str) -> list[Any]:
        return [r for r, k in zip(self.rows, self.keys, strict=True) if k == key]


async def _load(session: AsyncSession) -> _Data:
    return _Data(list((await session.execute(_ROWS)).all()))


def _summary(data: _Data, games: list[Any]) -> dict[str, Any]:
    n = len(games)
    yellow = sum(r.hy + r.ay for r in games) / n
    red = sum((r.hr or 0) + (r.ar or 0) for r in games) / n
    league_yellow = sum(data.league[(r.code, r.start_year)][1] for r in games) / n
    league_red = sum(data.league[(r.code, r.start_year)][2] for r in games) / n
    return {
        "matches": n,
        "yellow": _round(yellow),
        "red": _round(red),
        "home_yellow": _round(sum(r.hy for r in games) / n),
        "away_yellow": _round(sum(r.ay for r in games) / n),
        "league_yellow": _round(league_yellow),
        "league_red": _round(league_red),
        "enough": n >= MIN_MATCHES,
    }


async def referee_profile(session: AsyncSession, name: str) -> dict[str, Any]:
    data = await _load(session)
    wanted = referee_key(name)
    games = data.by_key(wanted)
    if not games:
        raise NotFoundError(f"aucun match terminé avec cartons pour l'arbitre {name}")
    by_season: dict[tuple[str, int], list[Any]] = defaultdict(list)
    for r in games:
        by_season[(r.code, r.start_year)].append(r)
    seasons = [
        {"competition": comp, "season": year, **_summary(data, rows)}
        for (comp, year), rows in sorted(by_season.items(), key=lambda kv: -kv[0][1])
    ]
    recent = [
        {
            "match_id": r.id,
            "date": r.match_date,
            "competition": r.code,
            "home": r.home,
            "away": r.away,
            "home_yellow": r.hy,
            "away_yellow": r.ay,
            "red": (r.hr or 0) + (r.ar or 0),
        }
        for r in reversed(games[-RECENT_MATCHES:])
    ]
    return {
        "name": data.display[wanted],
        "min_matches": MIN_MATCHES,
        "total": _summary(data, games),
        "seasons": seasons,
        "recent": recent,
    }


async def referee_table(session: AsyncSession, competition: str, season: int) -> dict[str, Any]:
    data = await _load(session)
    code = competition.upper()
    if (code, season) not in data.league:
        raise NotFoundError(f"aucun match terminé avec cartons pour {code} {season}")
    n, league_yellow, league_red = data.league[(code, season)]
    by_ref: dict[str, list[Any]] = defaultdict(list)
    missing = 0
    for r, key in zip(data.rows, data.keys, strict=True):
        if r.code == code and r.start_year == season:
            if key is None:
                missing += 1
            else:
                by_ref[key].append(r)
    # Classés d'abord (au moins MIN_MATCHES matchs, du plus sévère au plus clément),
    # puis ceux qui ont trop peu de matchs pour être jugés.
    referees = sorted(
        ({"name": data.display[key], **_summary(data, rows)} for key, rows in by_ref.items()),
        key=lambda x: (not x["enough"], -(x["yellow"] or 0)),
    )
    return {
        "competition": code,
        "season": season,
        "matches": n,
        "league_yellow": _round(league_yellow),
        "league_red": _round(league_red),
        "min_matches": MIN_MATCHES,
        # Matchs sans arbitre connu : à compléter (ingest.sh coverage), jamais caché.
        "without_referee": missing,
        "referees": referees,
    }
