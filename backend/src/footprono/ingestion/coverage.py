"""Couverture des données : ce qui est collecté, par championnat et par saison.

Pour chaque championnat et chaque saison (matchs terminés seulement) : part des matchs
avec score à la mi-temps, statistiques football-data (tirs, corners, cartons),
arbitre, xG (Understat), statistiques API-Football du match et par mi-temps,
cotes de clôture. Chaque trou récupérable est listé avec la commande qui le
comble ; un trou qui ne l'est pas (la source n'a pas la donnée) est dit tel quel.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.ingestion.sources.api_football import HALF_SPLIT_FIRST_SEASON

COLUMNS = {
    "ht": "mi-temps",
    "fd_stats": "stats FD",
    "referee": "arbitre",
    "xg": "xG",
    "api_full": "stats API",
    "api_half": "par mi-t.",
    "closing_odds": "cotes",
}
COMPLETE = 0.98  # en dessous : à compléter (quelques matchs manquent parfois à la source)

_QUERY = text(
    """
    select c.code as competition, s.start_year as season, count(*) as matches,
      avg((m.home_goals_ht is not null)::int) as ht,
      avg((m.home_corners is not null)::int) as fd_stats,
      avg((coalesce(m.referee, m.api_referee) is not null)::int) as referee,
      avg((exists(select 1 from match_advanced_stats a where a.match_id = m.id))::int) as xg,
      avg((exists(select 1 from match_team_stats t
                  where t.match_id = m.id and t.period = 'full'))::int) as api_full,
      avg((exists(select 1 from match_team_stats t
                  where t.match_id = m.id and t.period = 'first_half'))::int) as api_half,
      avg((exists(select 1 from match_odds o
                  where o.match_id = m.id and o.timing = 'close'))::int) as closing_odds
    from matches m
    join seasons s on s.id = m.season_id
    join competitions c on c.id = s.competition_id
    where m.status = 'finished'
    group by c.code, s.start_year
    order by c.code, s.start_year
    """
)


def _todo(rows: list[dict[str, Any]]) -> list[str]:
    """Trous récupérables, regroupés en commandes ; trous sans remède signalés."""
    by_fix: dict[tuple[str, str], dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    out: list[str] = []
    for r in rows:
        comp, season = r["competition"], r["season"]
        if r["api_full"] < COMPLETE or (
            season >= HALF_SPLIT_FIRST_SEASON and r["api_half"] < COMPLETE
        ):
            by_fix[("api-football", "statistiques API-Football")][comp].add(season)
        elif r["referee"] < COMPLETE:
            # La liste des matchs (1 requête par saison) donne l'arbitre ; les
            # statistiques déjà en base ne sont pas redemandées.
            by_fix[("api-football", "arbitres (liste des matchs API-Football)")][comp].add(season)
        if r["xg"] < COMPLETE:
            by_fix[("understat", "xG Understat")][comp].add(season)
        if r["fd_stats"] < COMPLETE or r["ht"] < COMPLETE or r["closing_odds"] < COMPLETE:
            by_fix[("football-data", "statistiques, mi-temps ou cotes football-data")][comp].add(
                season
            )
    for (source, what), comps in by_fix.items():
        seasons = sorted({y for ys in comps.values() for y in ys})
        out.append(
            f"{what} : {', '.join(f'{c} {_years(ys)}' for c, ys in sorted(comps.items()))}\n"
            f"    bash scripts/termux/ingest.sh {source} --seasons {','.join(map(str, seasons))} "
            f"--competitions {','.join(sorted(comps))}"
        )
    return out


def _years(years: set[int]) -> str:
    return ", ".join(f"{y}-{(y + 1) % 100:02d}" for y in sorted(years))


async def coverage_report(session: AsyncSession) -> dict[str, Any]:
    rows = [dict(r) for r in (await session.execute(_QUERY)).mappings().all()]
    for r in rows:
        for k in COLUMNS:
            r[k] = float(r[k])
    return {"rows": rows, "todo": _todo(rows)}


def format_coverage(report: dict[str, Any]) -> str:
    def cell(r: dict[str, Any], k: str) -> str:
        v = r[k]
        if k == "api_half" and r["season"] < HALF_SPLIT_FIRST_SEASON:
            return f"{'—':>10}"  # la source ne l'a pas : rien à récupérer
        return f"{v:>10.0%}" if v >= COMPLETE else f"{v:>9.0%}*"

    lines = [
        "Couverture des données (matchs terminés ; * = incomplet, — = la source ne l'a pas)",
        "",
        f"{'Championnat':<11}{'saison':>9}{'matchs':>7}"
        + "".join(f"{h:>10}" for h in COLUMNS.values()),
    ]
    for r in report["rows"]:
        lines.append(
            f"{r['competition']:<11}{_years({r['season']}):>9}{r['matches']:>7}"
            + "".join(cell(r, k) for k in COLUMNS)
        )
    lines += [
        "",
        f"Statistiques par mi-temps : API-Football les fournit à partir de "
        f"{_years({HALF_SPLIT_FIRST_SEASON})} seulement.",
        "",
        "À compléter :" if report["todo"] else "À compléter : rien, tout est collecté.",
    ]
    lines += [f"  - {t}" for t in report["todo"]]
    return "\n".join(lines)
