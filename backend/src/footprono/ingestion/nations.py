"""Sélections nationales (CAN, Coupe du Monde, Euro, Copa, Ligue des Nations,
éliminatoires, amicaux) : matchs en base.

- Source : API-Football (``/fixtures``), résultats seulement (aucune statistique). Même
  chargeur que les coupes d'Europe (ingestion/cups.py), avec trois différences :
  équipes créées au pays « Sélections » ; jamais reliées à une équipe existante par leur
  nom (seulement par leur identifiant API-Football, alias « #id ») ; terrain neutre en
  phase finale sauf pour le pays hôte chez lui (reference.FINAL_PHASES).
- Score retenu : celui du temps réglementaire, celui des paris.
- Jamais mêlées aux modèles des championnats ni des coupes (reference.NON_LEAGUE_CODES).
"""

import asyncio
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.core.config import Settings
from footprono.football.models import Competition, DataSource, Match, Season, Team, TeamAlias
from footprono.ingestion import service
from footprono.ingestion.cups import CupFixture, load_cup_fixtures
from footprono.ingestion.nation_names import french_name
from footprono.ingestion.reference import NATIONS, NATIONS_BY_CODE, nation_neutral
from footprono.ingestion.sources import api_football

NATION_COUNTRY = "Sélections"


def _noop(_message: str) -> None:
    return None


async def sync_nations(session: AsyncSession) -> None:
    for n in NATIONS:
        values = {
            "code": n.code, "name": n.name, "country": NATION_COUNTRY, "n_teams": 0,
            "football_data_division": None, "understat_slug": None,
            "api_football_id": n.api_football_id,
        }  # fmt: skip
        await session.execute(
            insert(Competition)
            .values(**values)
            .on_conflict_do_update(index_elements=["code"], set_=values)
        )
    await rename_nations(session)


async def rename_nations(session: AsyncSession) -> int:
    """Sélections déjà en base nommées en français (« Scotland » → « Écosse ») ; renvoie le
    nombre de renommées. Rattachement par numéro API-Football : rien d'autre ne change."""
    suffix = f" ({NATION_COUNTRY})"
    teams = (await session.scalars(select(Team).where(Team.country == NATION_COUNTRY))).all()
    taken = set((await session.scalars(select(Team.name))).all())
    renamed = 0
    for team in teams:
        base = team.name.removesuffix(suffix)
        wanted = french_name(base)
        if wanted == base:
            continue
        name = wanted if wanted not in taken else f"{wanted}{suffix}"
        if name in taken:
            continue
        taken.discard(team.name)
        team.name = name
        taken.add(name)
        renamed += 1
    if renamed:
        await session.flush()
    return renamed


def _neutral(code: str) -> Callable[[CupFixture], bool]:
    def neutral(f: CupFixture) -> bool:
        return nation_neutral(code, f.season, f.kickoff.date(), f.home[0], f.city)

    return neutral


async def official_team_ids(session: AsyncSession) -> set[int]:
    """Identifiants API-Football des sélections qui ont joué une compétition officielle."""
    codes = [n.code for n in NATIONS if n.official]
    in_official = (
        select(Match.home_team_id.label("team"))
        .join(Season, Season.id == Match.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .where(Competition.code.in_(codes))
    )
    teams = union(
        in_official,
        select(Match.away_team_id)
        .join(Season, Season.id == Match.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .where(Competition.code.in_(codes)),
    ).subquery()
    aliases = await session.scalars(
        select(TeamAlias.alias).where(
            TeamAlias.source == DataSource.API_FOOTBALL,
            TeamAlias.alias.startswith("#"),
            TeamAlias.team_id.in_(select(teams.c.team)),
        )
    )
    return {int(a[1:]) for a in aliases}


def _between(item: dict[str, Any], teams: set[int]) -> bool:
    return {item["teams"]["home"]["id"], item["teams"]["away"]["id"]} <= teams


async def load_nation_fixtures(
    session: AsyncSession, code: str, items: list[dict[str, Any]]
) -> dict[str, int]:
    """Crée ou met à jour les matchs d'une compétition de sélections.

    Amicaux : API-Football y mêle des matchs de clubs et d'équipes de jeunes (U17 à U23 ;
    603 des 928 « amicaux » de 2026). Seuls ceux entre deux sélections qui ont joué une
    compétition officielle sont gardés."""
    skipped = 0
    if not NATIONS_BY_CODE[code].official:
        teams = await official_team_ids(session)
        kept = [i for i in items if _between(i, teams)]
        skipped, items = len(items) - len(kept), kept
    stats = await load_cup_fixtures(
        session, code, items, country=NATION_COUNTRY, by_name=False, neutral=_neutral(code)
    )
    return {**stats, "skipped": skipped}


def _read_archive(archive_dir: Path) -> dict[str, list[tuple[str, list[dict[str, Any]]]]]:
    """Fichiers de l'archive par compétition : (saison, matchs) ; lecture hors boucle."""
    out: dict[str, list[tuple[str, list[dict[str, Any]]]]] = {}
    for code in NATIONS_BY_CODE:
        base = archive_dir.expanduser() / code
        paths = sorted(base.glob("*/fixtures.json")) if base.is_dir() else []
        out[code] = [(p.parent.name, json.loads(p.read_text())) for p in paths]
    return out


async def import_nations_archive(
    session: AsyncSession, archive_dir: Path, log: Callable[[str], None] = _noop
) -> dict[str, Any]:
    """Historique des sélections depuis l'archive API-Football (un dossier par code)."""
    await sync_nations(session)
    files = await asyncio.to_thread(_read_archive, archive_dir)
    report: dict[str, Any] = {}
    for code, seasons in files.items():
        total = {"inserted": 0, "updated": 0, "finished": 0, "skipped": 0, "seasons": 0}
        for season, items in seasons:
            stats = await load_nation_fixtures(session, code, items)
            for k, v in stats.items():
                total[k] += v
            total["seasons"] += 1
            log(
                f"{code} {season} : {stats['inserted']} ajoutés, {stats['updated']} mis à jour"
                + (f", {stats['skipped']} écartés (clubs, jeunes)" if stats["skipped"] else "")
            )
        if not seasons:
            log(f"{code} : rien dans l'archive")
        report[code] = total
    await session.commit()
    return report


async def update_nations(
    session: AsyncSession,
    settings: Settings,
    today: date | None = None,
    log: Callable[[str], None] = _noop,
) -> dict[str, Any]:
    """Saison en cours de chaque compétition : calendrier et résultats.

    La saison en cours n'a pas de règle commune (CAN tous les deux ans, éliminatoires sur
    deux ans, amicaux par année) : API-Football la donne (``/leagues?current=true``).
    Deux requêtes par compétition."""
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}
    await sync_nations(session)
    report: dict[str, Any] = {"status": "ok", "competitions": {}}
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=2 * len(NATIONS) + 1,
        min_remaining=settings.api_football_min_remaining,
        transport=service.api_football_transport,
    ) as client:
        await client.status()
        for n in NATIONS:
            body = await client.get("/leagues", {"id": n.api_football_id, "current": "true"})
            seasons = [
                int(s["year"])
                for league in body.get("response", [])
                for s in league.get("seasons", [])
                if s.get("current")
            ]
            if not seasons:
                report["competitions"][n.code] = {"season": None}
                continue
            season = max(seasons)
            fixtures = await client.get(
                "/fixtures", {"league": n.api_football_id, "season": season}
            )
            stats = await load_nation_fixtures(session, n.code, fixtures.get("response", []))
            report["competitions"][n.code] = {"season": season, **stats}
            log(f"{n.code} {season} : {stats}")
        report["requests"] = client.used
    await session.commit()
    return report
