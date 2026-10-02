"""Fiche équipe et « classement mérité » : les données collectées, montrées telles quelles.

Faits seulement (matchs terminés d'une saison de championnat), aucune estimation :
- football-data : buts, tirs cadrés, corners, cartons ;
- Understat : xG, xG concédés, pressing (PPDA = passes adverses par action
  défensive, plus bas = plus intense), passes dangereuses (« deep »), xPts ;
- API-Football (match complet) : possession, arrêts du gardien, réussite des passes.

Classement mérité : points réels contre xPts d'Understat (points qu'une équipe
obtiendrait en moyenne avec la qualité de ses occasions et de celles concédées).
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.core.errors import NotFoundError
from footprono.football.analysis import _form

# Statistiques avancées (Understat, API-Football) : réservées à Premium.
PREMIUM_FIELDS = (
    "xg_for",
    "xg_against",
    "xpts",
    "ppda",
    "deep",
    "shots_on_target",
    "corners",
    "yellow_cards",
    "possession",
    "saves",
    "pass_pct",
)

# Écart de points sous lequel la différence réel / mérité relève du hasard ordinaire.
LUCK_THRESHOLD = 3.0
MIN_MATCHES_DEFAULT = 5  # saison par défaut : la plus récente avec au moins 5 matchs joués

_VENUE = {"home": "m.home_team_id = :team", "away": "m.away_team_id = :team"}

_PROFILE = """
select count(*) as matches,
  avg(case when m.home_team_id = :team then m.home_goals else m.away_goals end) as goals_for,
  avg(case when m.home_team_id = :team then m.away_goals else m.home_goals end) as goals_against,
  sum(case when (m.home_team_id = :team and m.home_goals > m.away_goals)
            or (m.away_team_id = :team and m.away_goals > m.home_goals) then 3
           when m.home_goals = m.away_goals then 1 else 0 end) as points,
  avg(case when m.home_team_id = :team then m.home_shots_on_target
           else m.away_shots_on_target end) as shots_on_target,
  avg(case when m.home_team_id = :team then m.home_corners else m.away_corners end) as corners,
  avg(case when m.home_team_id = :team then m.home_yellow_cards
           else m.away_yellow_cards end) as yellow_cards,
  avg(a.xg) as xg_for, avg(a.xga) as xg_against, sum(a.xpts) as xpts,
  avg(a.ppda_att::numeric / nullif(a.ppda_def, 0)) as ppda, avg(a.deep) as deep,
  avg(t.possession) as possession, avg(t.goalkeeper_saves) as saves,
  avg(t.passes_pct) as pass_pct
from matches m
left join match_advanced_stats a
  on a.match_id = m.id and a.team_id = :team and a.source = 'understat'
left join match_team_stats t
  on t.match_id = m.id and t.team_id = :team and t.period = 'full'
  and t.source = 'api_football'
where m.season_id = :season and m.status = 'finished'
  and m.home_goals is not null and m.away_goals is not null
  and ({venue})
"""

_MERITED = """
with played as (
  select m.home_team_id as team, m.id,
         case when m.home_goals > m.away_goals then 3
              when m.home_goals = m.away_goals then 1 else 0 end as pts,
         m.home_goals as gf, m.away_goals as ga
  from matches m
  where m.season_id = :season and m.status = 'finished' and m.home_goals is not null
  union all
  select m.away_team_id, m.id,
         case when m.away_goals > m.home_goals then 3
              when m.home_goals = m.away_goals then 1 else 0 end,
         m.away_goals, m.home_goals
  from matches m
  where m.season_id = :season and m.status = 'finished' and m.home_goals is not null
)
select tm.id, tm.name, count(*) as played, sum(p.pts) as points, sum(p.gf) as gf,
       sum(p.ga) as ga, sum(a.xpts) as xpts, sum(a.xg) as xg, sum(a.xga) as xga,
       count(a.xpts) as with_xpts
from played p
join teams tm on tm.id = p.team
left join match_advanced_stats a
  on a.match_id = p.id and a.team_id = p.team and a.source = 'understat'
group by tm.id, tm.name
order by points desc, sum(p.gf) - sum(p.ga) desc, sum(p.gf) desc, tm.name
"""


def _num(value: Any, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


async def _season_id(session: AsyncSession, competition: str, year: int) -> int:
    found = await session.scalar(
        text(
            "select s.id from seasons s join competitions c on c.id = s.competition_id "
            "where c.code = :code and s.start_year = :year"
        ),
        {"code": competition.upper(), "year": year},
    )
    if found is None:
        raise NotFoundError(f"saison {competition} {year} introuvable")
    return int(found)


async def team_seasons(session: AsyncSession, team_id: int) -> list[dict[str, Any]]:
    """Saisons de championnat de l'équipe avec leur nombre de matchs joués, récentes d'abord."""
    rows = await session.execute(
        text(
            """
            select c.code, s.start_year, count(m.id) filter (where m.status = 'finished')
            from matches m
            join seasons s on s.id = m.season_id
            join competitions c on c.id = s.competition_id
            where m.home_team_id = :team or m.away_team_id = :team
            group by c.code, s.start_year
            order by s.start_year desc, c.code
            """
        ),
        {"team": team_id},
    )
    return [{"competition": c, "season": y, "played": int(n)} for c, y, n in rows.tuples()]


async def team_profile(
    session: AsyncSession,
    team_id: int,
    competition: str | None = None,
    season: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    team = await session.scalar(text("select name from teams where id = :t"), {"t": team_id})
    if team is None:
        raise NotFoundError(f"équipe {team_id} introuvable")
    seasons = await team_seasons(session, team_id)
    if not seasons:
        raise NotFoundError(f"aucun match pour l'équipe {team_id}")
    chosen: dict[str, Any] | None
    if season is None:
        chosen = next((s for s in seasons if s["played"] >= MIN_MATCHES_DEFAULT), seasons[0])
    else:
        chosen = next(
            (
                s
                for s in seasons
                if s["season"] == season
                and (competition is None or s["competition"] == competition.upper())
            ),
            None,
        )
        if chosen is None:
            raise NotFoundError(f"l'équipe {team} n'a pas joué la saison {season}")
    season_id = await _season_id(session, chosen["competition"], chosen["season"])
    venues: dict[str, Any] = {}
    for name, cond in (*_VENUE.items(), ("all", " or ".join(_VENUE.values()))):
        row = (
            (
                await session.execute(
                    text(_PROFILE.format(venue=cond)), {"team": team_id, "season": season_id}
                )
            )
            .mappings()
            .one()
        )
        venues[name] = {
            "matches": int(row["matches"]),
            "points": int(row["points"] or 0),
            "goals_for": _num(row["goals_for"]),
            "goals_against": _num(row["goals_against"]),
            "xg_for": _num(row["xg_for"]),
            "xg_against": _num(row["xg_against"]),
            "xpts": _num(row["xpts"], 1),
            "ppda": _num(row["ppda"], 1),
            "deep": _num(row["deep"], 1),
            "shots_on_target": _num(row["shots_on_target"], 1),
            "corners": _num(row["corners"], 1),
            "yellow_cards": _num(row["yellow_cards"], 1),
            "possession": _num(row["possession"], 1),
            "saves": _num(row["saves"], 1),
            "pass_pct": _num(row["pass_pct"], 1),
        }
    day = (today or date.today()) + timedelta(days=1)
    return {
        "team": {"id": team_id, "name": team},
        "competition": chosen["competition"],
        "season": chosen["season"],
        "seasons": [s for s in seasons if s["played"] > 0],
        "form": await _form(session, team_id, day),
        "venues": venues,
    }


async def merited_table(session: AsyncSession, competition: str, season: int) -> dict[str, Any]:
    season_id = await _season_id(session, competition, season)
    rows = (await session.execute(text(_MERITED), {"season": season_id})).mappings().all()
    complete = all(r["with_xpts"] == r["played"] for r in rows)
    by_xpts = sorted((r for r in rows if r["xpts"] is not None), key=lambda r: -float(r["xpts"]))
    xrank = {r["id"]: i + 1 for i, r in enumerate(by_xpts)}
    table = []
    for i, r in enumerate(rows, start=1):
        xpts = _num(r["xpts"], 1)
        luck = None if xpts is None else round(int(r["points"]) - xpts, 1)
        table.append(
            {
                "rank": i,
                "merited_rank": xrank.get(r["id"]),
                "team": {"id": r["id"], "name": r["name"]},
                "played": int(r["played"]),
                "points": int(r["points"]),
                "goals_for": int(r["gf"]),
                "goals_against": int(r["ga"]),
                "xpts": xpts,
                "xg_for": _num(r["xg"], 1),
                "xg_against": _num(r["xga"], 1),
                "luck": luck,
                "verdict": (
                    None
                    if luck is None
                    else "lucky"
                    if luck >= LUCK_THRESHOLD
                    else "unlucky"
                    if luck <= -LUCK_THRESHOLD
                    else "fair"
                ),
            }
        )
    return {
        "competition": competition.upper(),
        "season": season,
        "luck_threshold": LUCK_THRESHOLD,
        # Faux si Understat n'a pas encore les xPts de quelques matchs : le dire.
        "complete": complete,
        "table": table,
    }


def lock_premium(profile: dict[str, Any]) -> dict[str, Any]:
    """Version gratuite : forme, buts et points ; les statistiques avancées sont masquées."""
    for venue in profile["venues"].values():
        for field in PREMIUM_FIELDS:
            venue[field] = None
    profile["locked"] = True
    return profile
