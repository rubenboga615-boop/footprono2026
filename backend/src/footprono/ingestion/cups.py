"""Coupes d'Europe (Ligue des Champions, Ligue Europa, Ligue Conférence) : matchs en base.

- Source : API-Football (``/fixtures``), résultats seulement. L'historique vient de
  l'archive collectée depuis la console, la saison en cours d'une requête par coupe.
- Une équipe d'un de nos championnats est reconnue par son nom API-Football
  (référentiel) ; une équipe d'un autre pays est créée (pays « Europe ») et retrouvée
  ensuite par son identifiant API-Football (alias « #id »).
- Score retenu : celui du temps réglementaire (``score.fulltime``), celui des paris ;
  prolongation et tirs au but n'y comptent pas. Finale : terrain neutre.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.core.config import Settings
from footprono.football.models import Competition, DataSource, Match, MatchStatus, Team, TeamAlias
from footprono.ingestion import service
from footprono.ingestion.loader import season_id
from footprono.ingestion.reference import CUP_ARCHIVE_DIRS, CUPS, CUPS_BY_CODE, cup_season
from footprono.ingestion.sources import api_football

FINISHED = frozenset({"FT", "AET", "PEN"})
CANCELLED = frozenset({"CANC", "ABD", "AWD", "WO"})
CUP_COUNTRY = "Europe"


@dataclass(frozen=True)
class CupFixture:
    fixture_id: int
    season: int
    round: str
    kickoff: datetime
    home: tuple[str, int]  # nom et identifiant API-Football
    away: tuple[str, int]
    status: str
    fulltime: tuple[int, int] | None
    halftime: tuple[int, int] | None

    @property
    def neutral(self) -> bool:
        return self.round.strip().lower() == "final"


def _score(part: dict[str, Any] | None) -> tuple[int, int] | None:
    if not part or part.get("home") is None or part.get("away") is None:
        return None
    return int(part["home"]), int(part["away"])


def parse_fixture(item: dict[str, Any]) -> CupFixture:
    fx, teams, score = item["fixture"], item["teams"], item.get("score") or {}
    return CupFixture(
        fixture_id=int(fx["id"]),
        season=int(item["league"]["season"]),
        round=str(item["league"].get("round") or "")[:60],
        kickoff=datetime.fromisoformat(str(fx["date"])).astimezone(UTC),
        home=(str(teams["home"]["name"]), int(teams["home"]["id"])),
        away=(str(teams["away"]["name"]), int(teams["away"]["id"])),
        status=str((fx.get("status") or {}).get("short") or "NS"),
        fulltime=_score(score.get("fulltime")),
        halftime=_score(score.get("halftime")),
    )


async def sync_cups(session: AsyncSession) -> None:
    for cup in CUPS:
        values = {
            "code": cup.code, "name": cup.name, "country": CUP_COUNTRY, "n_teams": 36,
            "football_data_division": None, "understat_slug": None,
            "api_football_id": cup.api_football_id,
        }  # fmt: skip
        await session.execute(
            insert(Competition)
            .values(**values)
            .on_conflict_do_update(index_elements=["code"], set_=values)
        )


async def _team_ids(session: AsyncSession, teams: dict[int, str]) -> dict[int, int]:
    """Identifiant API-Football → équipe en base (créée si elle n'existe pas)."""
    src = DataSource.API_FOOTBALL
    rows = (
        await session.execute(
            select(TeamAlias.alias, TeamAlias.team_id).where(TeamAlias.source == src)
        )
    ).tuples()
    aliases = dict(rows.all())
    by_name = dict((await session.execute(select(Team.name, Team.id))).tuples().all())
    out: dict[int, int] = {}
    for api_id, name in teams.items():
        team_id = aliases.get(f"#{api_id}") or aliases.get(name) or by_name.get(name)
        if team_id is None:
            team_id = await session.scalar(
                insert(Team).values(name=name, country=CUP_COUNTRY).returning(Team.id)
            )
            assert team_id is not None
            by_name[name] = team_id
        for alias in (f"#{api_id}", name):
            if alias not in aliases:
                await session.execute(
                    insert(TeamAlias)
                    .values(team_id=team_id, source=src, alias=alias)
                    .on_conflict_do_nothing(index_elements=["source", "alias"])
                )
                aliases[alias] = team_id
        out[api_id] = team_id
    return out


async def load_cup_fixtures(
    session: AsyncSession, code: str, items: list[dict[str, Any]]
) -> dict[str, int]:
    """Crée ou met à jour les matchs d'une coupe (retrouvés par identifiant API-Football)."""
    fixtures = [parse_fixture(i) for i in items]
    teams = await _team_ids(session, {t[1]: t[0] for f in fixtures for t in (f.home, f.away)})
    existing = {
        m.api_football_id: m
        for m in (
            await session.scalars(
                select(Match).where(Match.api_football_id.in_([f.fixture_id for f in fixtures]))
            )
        ).all()
    }
    seasons: dict[int, int] = {}
    stats = {"inserted": 0, "updated": 0, "finished": 0}
    for f in sorted(fixtures, key=lambda f: (f.kickoff, f.fixture_id)):
        if f.season not in seasons:
            seasons[f.season] = await season_id(session, code, f.season)
        home, away = teams[f.home[1]], teams[f.away[1]]
        if home == away:
            continue
        finished = f.status in FINISHED and f.fulltime is not None
        status = (
            MatchStatus.FINISHED
            if finished
            else MatchStatus.CANCELLED
            if f.status in CANCELLED
            else MatchStatus.SCHEDULED
        )
        values: dict[str, Any] = {
            "match_date": f.kickoff.date(),
            "kickoff_at": f.kickoff,
            "status": status,
            "home_goals": f.fulltime[0] if finished and f.fulltime else None,
            "away_goals": f.fulltime[1] if finished and f.fulltime else None,
            "home_goals_ht": f.halftime[0] if finished and f.halftime else None,
            "away_goals_ht": f.halftime[1] if finished and f.halftime else None,
            "api_status": f.status[:8],
            "round": f.round,
            "neutral": f.neutral,
            "result_source": "api_football" if finished else None,
        }
        stats["finished"] += finished
        match = existing.get(f.fixture_id)
        if match is not None:
            for k, v in values.items():
                setattr(match, k, v)
            stats["updated"] += 1
            continue
        # Une affiche peut revenir dans la saison (qualifications puis phase de ligue).
        leg = (
            await session.scalar(
                select(func.coalesce(func.max(Match.leg), 0)).where(
                    Match.season_id == seasons[f.season],
                    Match.home_team_id == home,
                    Match.away_team_id == away,
                )
            )
            or 0
        ) + 1
        session.add(
            Match(
                season_id=seasons[f.season], home_team_id=home, away_team_id=away, leg=leg,
                api_football_id=f.fixture_id, **values,
            )
        )  # fmt: skip
        await session.flush()
        stats["inserted"] += 1
    return stats


def _noop(_message: str) -> None:
    return None


def _read_archive(archive_dir: Path) -> dict[str, list[tuple[str, list[dict[str, Any]]]]]:
    """Fichiers de l'archive par coupe : (saison, matchs) ; lecture du disque hors boucle."""
    out: dict[str, list[tuple[str, list[dict[str, Any]]]]] = {}
    for code, folder in CUP_ARCHIVE_DIRS.items():
        base = archive_dir.expanduser() / folder
        paths = sorted(base.glob("*/fixtures.json")) if base.is_dir() else []
        out[code] = [(p.parent.name, json.loads(p.read_text())) for p in paths]
    return out


async def import_cup_archive(
    session: AsyncSession, archive_dir: Path, log: Callable[[str], None] = _noop
) -> dict[str, Any]:
    """Historique des coupes depuis l'archive API-Football (dossiers UCL, UEL, UECL)."""
    await sync_cups(session)
    files = await asyncio.to_thread(_read_archive, archive_dir)
    report: dict[str, Any] = {}
    for code, seasons in files.items():
        total = {"inserted": 0, "updated": 0, "finished": 0, "seasons": 0}
        for season, items in seasons:
            stats = await load_cup_fixtures(session, code, items)
            for k, v in stats.items():
                total[k] += v
            total["seasons"] += 1
            log(f"{code} {season} : {stats['inserted']} ajoutés, {stats['updated']} mis à jour")
        if not seasons:
            log(f"{code} : rien dans l'archive")
        report[code] = total
    await session.commit()
    return report


async def update_cups(
    session: AsyncSession,
    settings: Settings,
    today: date | None = None,
    log: Callable[[str], None] = _noop,
) -> dict[str, Any]:
    """Saison en cours des coupes : calendrier et résultats (une requête par coupe)."""
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}
    await sync_cups(session)
    season = cup_season(today)
    report: dict[str, Any] = {"status": "ok", "season": season, "cups": {}}
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=len(CUPS) + 1,
        min_remaining=settings.api_football_min_remaining,
        transport=service.api_football_transport,
    ) as client:
        await client.status()
        for cup in CUPS_BY_CODE.values():
            body = await client.get("/fixtures", {"league": cup.api_football_id, "season": season})
            stats = await load_cup_fixtures(session, cup.code, body.get("response", []))
            report["cups"][cup.code] = stats
            log(f"{cup.code} {season} : {stats}")
        report["requests"] = client.used
    await session.commit()
    return report
