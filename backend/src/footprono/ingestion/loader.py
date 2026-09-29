"""Chargement des données normalisées en base.

Règles :
- un nom d'équipe inconnu du référentiel rejette tout le fichier (erreur
  explicite) : aucun match n'est rattaché à une mauvaise équipe ni ignoré ;
- football-data fait foi pour les résultats et statistiques ;
- Understat complète (xG, matchs à venir) sans jamais écraser football-data,
  et tout désaccord de score est signalé ;
- toutes les écritures sont idempotentes (relancer ne crée pas de doublon).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Result, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.football.models import (
    Competition,
    DataSource,
    Match,
    MatchAdvancedStats,
    MatchOdds,
    MatchStatus,
    Season,
    Team,
    TeamAlias,
)
from footprono.ingestion.reference import COMPETITIONS, INTERRUPTED_SEASONS, load_teams
from footprono.ingestion.sources.football_data import FootballDataMatch
from footprono.ingestion.sources.understat import UnderstatSeason

# asyncpg limite une requête à 32 767 paramètres.
_CHUNK = 2000


class UnknownTeamsError(Exception):
    def __init__(self, source: DataSource, names: Iterable[str]) -> None:
        self.names = sorted(set(names))
        super().__init__(
            f"équipes inconnues du référentiel ({source.value}) : {', '.join(self.names)}"
        )


@dataclass
class LoadStats:
    matches_inserted: int = 0
    matches_updated: int = 0
    odds_upserted: int = 0
    advanced_stats_upserted: int = 0
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "matches_inserted": self.matches_inserted,
            "matches_updated": self.matches_updated,
            "odds_upserted": self.odds_upserted,
            "advanced_stats_upserted": self.advanced_stats_upserted,
            "issues": self.issues,
        }


def _chunks(
    rows: Sequence[dict[str, Any]], size: int = _CHUNK
) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


async def sync_reference(session: AsyncSession) -> None:
    """Crée ou met à jour compétitions, équipes et alias depuis le référentiel."""
    for comp in COMPETITIONS:
        values = {
            "code": comp.code,
            "name": comp.name,
            "country": comp.country,
            "n_teams": comp.n_teams,
            "football_data_division": comp.football_data_division,
            "understat_slug": comp.understat_slug,
            "api_football_id": comp.api_football_id,
        }
        await session.execute(
            insert(Competition)
            .values(**values)
            .on_conflict_do_update(index_elements=["code"], set_=values)
        )

    country = {c.code: c.country for c in COMPETITIONS}
    for team in load_teams():
        await session.execute(
            insert(Team)
            .values(name=team.name, country=country[team.competition])
            .on_conflict_do_update(
                index_elements=["name"], set_={"country": country[team.competition]}
            )
        )
    team_ids = dict((await session.execute(select(Team.name, Team.id))).tuples().all())
    alias_rows = [
        {"team_id": team_ids[team.name], "source": source, "alias": alias}
        for team in load_teams()
        for source, alias in team.aliases.items()
    ]
    stmt = insert(TeamAlias)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["source", "alias"], set_={"team_id": stmt.excluded.team_id}
        ),
        alias_rows,
    )


class TeamResolver:
    def __init__(self, aliases: dict[tuple[DataSource, str], int]) -> None:
        self._aliases = aliases

    @classmethod
    async def load(cls, session: AsyncSession) -> "TeamResolver":
        rows = await session.execute(select(TeamAlias.source, TeamAlias.alias, TeamAlias.team_id))
        return cls({(source, alias): team_id for source, alias, team_id in rows.tuples()})

    def resolve_all(self, source: DataSource, names: Iterable[str]) -> dict[str, int]:
        names = set(names)
        resolved = {n: self._aliases[(source, n)] for n in names if (source, n) in self._aliases}
        missing = names - resolved.keys()
        if missing:
            raise UnknownTeamsError(source, missing)
        return resolved


async def season_id(session: AsyncSession, competition_code: str, start_year: int) -> int:
    competition_id = await session.scalar(
        select(Competition.id).where(Competition.code == competition_code)
    )
    if competition_id is None:
        raise ValueError(f"compétition inconnue : {competition_code}")
    await session.execute(
        insert(Season)
        .values(competition_id=competition_id, start_year=start_year)
        .on_conflict_do_nothing(index_elements=["competition_id", "start_year"])
    )
    sid = await session.scalar(
        select(Season.id).where(
            Season.competition_id == competition_id, Season.start_year == start_year
        )
    )
    assert sid is not None
    return sid


async def load_football_data(
    session: AsyncSession,
    competition_code: str,
    start_year: int,
    matches: list[FootballDataMatch],
    raw_file_id: int,
    resolver: TeamResolver,
) -> LoadStats:
    stats = LoadStats()
    teams = resolver.resolve_all(
        DataSource.FOOTBALL_DATA, [n for m in matches for n in (m.home_team, m.away_team)]
    )
    sid = await season_id(session, competition_code, start_year)

    seen: set[tuple[int, int]] = set()
    rows: list[dict[str, Any]] = []
    for m in matches:
        key = (teams[m.home_team], teams[m.away_team])
        if key in seen:
            stats.issues.append(f"affiche en double ignorée : {m.home_team} - {m.away_team}")
            continue
        seen.add(key)
        rows.append(
            {
                "season_id": sid,
                "home_team_id": key[0],
                "away_team_id": key[1],
                "match_date": m.match_date,
                "kickoff_time": m.kickoff_time,
                "status": MatchStatus.FINISHED if m.finished else MatchStatus.SCHEDULED,
                "home_goals": m.home_goals,
                "away_goals": m.away_goals,
                "home_goals_ht": m.home_goals_ht,
                "away_goals_ht": m.away_goals_ht,
                "referee": m.referee,
                "football_data_file_id": raw_file_id,
                **m.stats,
            }
        )
    if not rows:
        return stats
    await _drop_contradicted_fixtures(session, sid, rows, stats)

    match_ids: dict[tuple[int, int], int] = {}
    for chunk in _chunks(rows):
        stmt = insert(Match).values(list(chunk))
        updatable = {
            k: stmt.excluded[k]
            for k in chunk[0]
            if k not in ("season_id", "home_team_id", "away_team_id")
        }
        result: Result[Any] = await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["season_id", "home_team_id", "away_team_id"], set_=updatable
            ).returning(
                Match.id,
                Match.home_team_id,
                Match.away_team_id,
                literal_column("(xmax = 0)").label("inserted"),
            )
        )
        for match_id, home_id, away_id, inserted in result.tuples():
            match_ids[(home_id, away_id)] = match_id
            if inserted:
                stats.matches_inserted += 1
            else:
                stats.matches_updated += 1

    odds_rows = [
        {
            "match_id": match_ids[(teams[m.home_team], teams[m.away_team])],
            "source": DataSource.FOOTBALL_DATA,
            "bookmaker": q.bookmaker,
            "market": q.market,
            "line": q.line,
            "timing": q.timing,
            "selection": q.selection,
            "price": q.price,
        }
        for m in matches
        if (teams[m.home_team], teams[m.away_team]) in match_ids
        for q in m.odds
    ]
    for chunk in _chunks(odds_rows):
        stmt = insert(MatchOdds).values(list(chunk))
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[
                    "match_id", "source", "bookmaker", "market", "line", "timing", "selection",
                ],
                set_={"price": stmt.excluded.price},
            )
        )  # fmt: skip
        stats.odds_upserted += len(chunk)
    return stats


async def _drop_contradicted_fixtures(
    session: AsyncSession, sid: int, rows: Sequence[dict[str, Any]], stats: LoadStats
) -> None:
    """Retire les rencontres créées par une autre source que football-data contredisant ce fichier.

    football-data fait foi : si une affiche absente de son fichier occupe, à ±1
    jour, la date d'un de ses matchs pour l'une des deux équipes, c'est l'autre
    source qui se trompe (domicile/extérieur inversés, date erronée…).
    """
    keys = {(r["home_team_id"], r["away_team_id"]) for r in rows}
    days: dict[int, set[date]] = {}
    for r in rows:
        for team in (r["home_team_id"], r["away_team_id"]):
            days.setdefault(team, set()).update(
                r["match_date"] + timedelta(days=k) for k in (-1, 0, 1)
            )
    others = (
        await session.scalars(
            select(Match).where(
                Match.season_id == sid,
                Match.football_data_file_id.is_(None),
                Match.status != MatchStatus.CANCELLED,
            )
        )
    ).all()
    for other in others:
        if (other.home_team_id, other.away_team_id) in keys:
            continue
        if any(
            other.match_date in days.get(t, ()) for t in (other.home_team_id, other.away_team_id)
        ):
            stats.issues.append(
                f"conflit entre sources : match {other.id} (hors football-data) du "
                f"{other.match_date} contredit football-data ; supprimé"
            )
            await session.delete(other)
    await session.flush()


async def load_understat(
    session: AsyncSession,
    competition_code: str,
    start_year: int,
    season: UnderstatSeason,
    raw_file_id: int,
    resolver: TeamResolver,
) -> LoadStats:
    stats = LoadStats(issues=list(season.issues.items))
    names = [n for m in season.matches for n in (m.home_team, m.away_team)]
    names += [t.team for t in season.team_matches]
    teams = resolver.resolve_all(DataSource.UNDERSTAT, names)
    sid = await season_id(session, competition_code, start_year)
    interrupted = (competition_code, start_year) in INTERRUPTED_SEASONS

    existing = {
        (row.home_team_id, row.away_team_id): row
        for row in (await session.execute(select(Match).where(Match.season_id == sid))).scalars()
    }

    # Dates déjà occupées par chaque équipe : une rencontre Understat absente
    # de la base qui tombe à ±1 jour d'un match connu de l'une des deux équipes
    # est une contradiction entre sources (domicile/extérieur inversés, date…).
    busy: dict[int, dict[date, Match]] = {}
    for row in existing.values():
        if row.status is not MatchStatus.CANCELLED:
            busy.setdefault(row.home_team_id, {})[row.match_date] = row
            busy.setdefault(row.away_team_id, {})[row.match_date] = row

    new_rows: list[dict[str, Any]] = []
    fixture_by_kickoff: dict[tuple[datetime, int], tuple[int, int]] = {}
    conflicts: set[tuple[datetime, int]] = set()
    source_ids: dict[tuple[int, int], str | None] = {}
    for m in season.matches:
        key = (teams[m.home_team], teams[m.away_team])
        clash = None
        if key not in existing:
            clash = next(
                (
                    busy[team][d]
                    for team in key
                    for d in (m.kickoff.date() + timedelta(days=k) for k in (-1, 0, 1))
                    if d in busy.get(team, {})
                ),
                None,
            )
        if clash is not None:
            stats.issues.append(
                f"conflit entre sources : Understat {m.home_team}-{m.away_team} "
                f"({m.home_goals}-{m.away_goals}) le {m.kickoff.date()} chevauche le match "
                f"{clash.id} déjà en base le {clash.match_date} "
                f"({clash.home_goals}-{clash.away_goals}) ; non inséré, xG non rattachés"
            )
            conflicts.update({(m.kickoff, key[0]), (m.kickoff, key[1])})
            continue
        fixture_by_kickoff[(m.kickoff, key[0])] = key
        fixture_by_kickoff[(m.kickoff, key[1])] = key
        source_ids[key] = m.source_id
        finished = m.is_result and m.home_goals is not None and m.away_goals is not None
        if finished:
            status = MatchStatus.FINISHED
        elif interrupted:
            status = MatchStatus.CANCELLED
        else:
            status = MatchStatus.SCHEDULED
        values = {
            "match_date": m.kickoff.date(),
            "status": status,
            "home_goals": m.home_goals if finished else None,
            "away_goals": m.away_goals if finished else None,
        }
        current = existing.get(key)
        if current is None:
            new_rows.append(
                {
                    "season_id": sid,
                    "home_team_id": key[0],
                    "away_team_id": key[1],
                    **values,
                }
            )
        elif current.status is MatchStatus.FINISHED:
            if finished and (current.home_goals, current.away_goals) != (
                m.home_goals,
                m.away_goals,
            ):
                stats.issues.append(
                    f"score en désaccord {m.home_team}-{m.away_team} : football-data "
                    f"{current.home_goals}-{current.away_goals}, Understat "
                    f"{m.home_goals}-{m.away_goals} (football-data conservé)"
                )
        elif values != {k: getattr(current, k) for k in values}:
            # Match pas encore joué en base : Understat peut apporter le
            # résultat ou une nouvelle date (report). football-data le
            # remplacera dès sa prochaine publication.
            await session.execute(update(Match).where(Match.id == current.id).values(**values))
            stats.matches_updated += 1

    for chunk in _chunks(new_rows):
        await session.execute(insert(Match).values(list(chunk)))
        stats.matches_inserted += len(chunk)

    match_ids = {
        (home, away): mid
        for mid, home, away in (
            await session.execute(
                select(Match.id, Match.home_team_id, Match.away_team_id).where(
                    Match.season_id == sid
                )
            )
        ).tuples()
    }

    adv_rows: list[dict[str, Any]] = []
    for t in season.team_matches:
        team_id = teams[t.team]
        if (t.kickoff, team_id) in conflicts:
            continue
        fixture = fixture_by_kickoff.get((t.kickoff, team_id))
        if fixture is None:
            stats.issues.append(f"stats Understat non rattachées : {t.team} le {t.kickoff}")
            continue
        expected_side = "h" if fixture[0] == team_id else "a"
        if t.side != expected_side:
            stats.issues.append(f"côté incohérent pour {t.team} le {t.kickoff}")
            continue
        adv_rows.append(
            {
                "match_id": match_ids[fixture],
                "team_id": team_id,
                "source": DataSource.UNDERSTAT,
                "source_match_id": source_ids.get(fixture),
                "xg": t.xg,
                "xga": t.xga,
                "npxg": t.npxg,
                "npxga": t.npxga,
                "ppda_att": t.ppda_att,
                "ppda_def": t.ppda_def,
                "ppda_allowed_att": t.ppda_allowed_att,
                "ppda_allowed_def": t.ppda_allowed_def,
                "deep": t.deep,
                "deep_allowed": t.deep_allowed,
                "xpts": t.xpts,
                "raw_file_id": raw_file_id,
            }
        )
    for chunk in _chunks(adv_rows):
        stmt = insert(MatchAdvancedStats).values(list(chunk))
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["match_id", "team_id", "source"],
                set_={
                    k: stmt.excluded[k]
                    for k in chunk[0]
                    if k not in ("match_id", "team_id", "source")
                },
            )
        )
        stats.advanced_stats_upserted += len(chunk)
    return stats
