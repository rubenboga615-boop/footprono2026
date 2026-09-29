"""Orchestration d'une ingestion : récupération, archivage, analyse, chargement, qualité.

Chaque fichier est traité dans sa propre transaction : l'échec d'un fichier
(source indisponible, équipe inconnue…) est consigné dans le rapport sans
annuler les autres. Le rapport complet est enregistré dans ``ingestion_runs``.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.core.config import Settings
from footprono.football.models import (
    Competition,
    DataSource,
    IngestionRun,
    Match,
    MatchTeamStats,
    Season,
    StatPeriod,
)
from footprono.ingestion import loader, raw_store
from footprono.ingestion.quality import run_quality_checks
from footprono.ingestion.reference import COMPETITIONS_BY_CODE, CompetitionRef, season_code
from footprono.ingestion.sources import api_football, football_data, understat
from footprono.ingestion.sources.common import ParseIssues

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionRequest:
    source: DataSource
    competitions: Sequence[str]
    seasons: Sequence[int]
    # Dossier local à importer ; ``None`` = téléchargement depuis la source.
    from_dir: Path | None = None


FileResult = dict[str, Any]


async def _football_data_file(
    session: AsyncSession,
    settings: Settings,
    comp: CompetitionRef,
    year: int,
    from_dir: Path | None,
) -> FileResult:
    code = season_code(year)
    division = comp.football_data_division
    if from_dir is None:
        origin = football_data.file_url(code, division)
        content = await raw_store.download(origin, headers={"Accept": "text/csv,text/plain,*/*"})
        if content.lstrip()[:1] == b"<":
            raise raw_store.SourceUnavailableError(
                f"{origin} : page HTML reçue au lieu du CSV (accès probablement bloqué)"
            )
    else:
        path = from_dir / code / f"{division}.csv"
        if not path.exists():
            raise raw_store.SourceUnavailableError(f"{path} : fichier absent", transient=False)
        origin, content = str(path), path.read_bytes()

    raw_id = await raw_store.archive(
        session,
        settings.raw_data_dir,
        DataSource.FOOTBALL_DATA,
        origin,
        f"{code}/{division}.csv",
        content,
    )
    matches, issues = football_data.parse_csv(content)
    resolver = await loader.TeamResolver.load(session)
    stats = await loader.load_football_data(session, comp.code, year, matches, raw_id, resolver)
    stats.issues[:0] = issues.items
    return {"origin": origin, "parsed_matches": len(matches), **stats.as_dict()}


async def _understat_file(
    session: AsyncSession,
    settings: Settings,
    comp: CompetitionRef,
    year: int,
    from_dir: Path | None,
) -> FileResult:
    slug = comp.understat_slug
    if from_dir is None:
        origin = understat.league_url(slug, year)
        content = await raw_store.download(
            origin,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://understat.com/league/{slug}/{year}",
            },
        )
        try:
            data = json.loads(content)
        except ValueError:
            head = content[:80].decode("utf-8", "replace").replace("\n", " ")
            raise raw_store.SourceUnavailableError(
                f"{origin} : réponse non JSON (accès probablement bloqué) : {head!r}"
            ) from None
        raw_id = await raw_store.archive(
            session,
            settings.raw_data_dir,
            DataSource.UNDERSTAT,
            origin,
            f"{year}/{slug}.json",
            content,
        )
        season = understat.parse_league_json(data)
    else:
        folder = from_dir / str(year) / slug
        matches_path, teams_path = folder / "matches.csv", folder / "team_matches.csv"
        if not (matches_path.exists() and teams_path.exists()):
            raise raw_store.SourceUnavailableError(
                f"{folder} : export Understat absent", transient=False
            )
        origin = str(folder)
        matches_csv, teams_csv = matches_path.read_bytes(), teams_path.read_bytes()
        raw_id = await raw_store.archive(
            session, settings.raw_data_dir, DataSource.UNDERSTAT, str(matches_path),
            f"{year}/{slug}-matches.csv", matches_csv,
        )  # fmt: skip
        await raw_store.archive(
            session, settings.raw_data_dir, DataSource.UNDERSTAT, str(teams_path),
            f"{year}/{slug}-team_matches.csv", teams_csv,
        )  # fmt: skip
        season = understat.parse_export_dir(matches_csv, teams_csv)

    resolver = await loader.TeamResolver.load(session)
    stats = await loader.load_understat(session, comp.code, year, season, raw_id, resolver)
    return {
        "origin": origin,
        "parsed_matches": len(season.matches),
        "parsed_team_matches": len(season.team_matches),
        **stats.as_dict(),
    }


# Progression à l'intérieur d'un fichier (téléchargement match par match).
PROGRESS_EVERY = 25
_progress: ContextVar[Callable[[str], None]] = ContextVar(
    "ingestion_progress", default=lambda _message: None
)

# Transport HTTP d'API-Football : remplaçable dans les tests, jamais en production.
api_football_transport: httpx.AsyncBaseTransport | None = None


async def _download_api_football(
    session: AsyncSession, settings: Settings, comp: CompetitionRef, year: int
) -> tuple[bytes, list[api_football.ApiFixture], list[str]]:
    """Liste des matchs terminés, puis statistiques de ceux qui n'en ont pas encore."""
    if settings.api_football_key is None:
        raise raw_store.SourceUnavailableError(
            "FP_API_FOOTBALL_KEY absente : statistiques API-Football non téléchargées",
            transient=False,
        )
    notes: list[str] = []
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=settings.api_football_budget,
        min_remaining=settings.api_football_min_remaining,
        transport=api_football_transport,
    ) as client:
        await client.status()
        body = await client.get("/fixtures", {"league": comp.api_football_id, "season": year})
        items = [i for i in body["response"] if api_football.is_finished_league_match(i)]
        done = set(
            (
                await session.scalars(
                    select(Match.api_football_id)
                    .join(Season, Season.id == Match.season_id)
                    .join(Competition, Competition.id == Season.competition_id)
                    .where(
                        Competition.code == comp.code,
                        Season.start_year == year,
                        Match.api_football_id.is_not(None),
                        select(MatchTeamStats.id)
                        .where(
                            MatchTeamStats.match_id == Match.id,
                            MatchTeamStats.source == DataSource.API_FOOTBALL,
                            MatchTeamStats.period == StatPeriod.FULL,
                        )
                        .exists(),
                    )
                )
            ).all()
        )
        params: dict[str, Any] = {}
        if year >= api_football.HALF_SPLIT_FIRST_SEASON:
            params["half"] = "true"
        statistics: dict[int, Any] = {}
        pending = [i for i in items if i["fixture"]["id"] not in done]
        notify = _progress.get()
        notify(f"    {len(items)} matchs terminés, {len(pending)} sans statistiques à demander")
        for n, item in enumerate(pending, start=1):
            if not client.can_spend():
                break
            fixture_id = item["fixture"]["id"]
            response = await client.get("/fixtures/statistics", {"fixture": fixture_id, **params})
            statistics[fixture_id] = response["response"]
            if n % PROGRESS_EVERY == 0:
                notify(f"    {n}/{len(pending)} — quota restant {client.day_remaining}")
        left = len(pending) - len(statistics)
        if left:
            notes.append(
                f"budget API-Football atteint : {left} matchs restent à demander "
                f"(quota restant {client.day_remaining}, réserve {client.min_remaining})"
            )

    issues = ParseIssues()
    fixtures = []
    for item in items:
        fixture = api_football.parse_fixture(item)
        if fixture.fixture_id in statistics:
            fixture.stats = api_football.parse_statistics(
                statistics[fixture.fixture_id], item["teams"]["home"]["id"], issues
            )
        fixtures.append(fixture)
    content = json.dumps({"fixtures": body, "statistics": statistics}).encode()
    return content, fixtures, notes + issues.items


async def _api_football_file(
    session: AsyncSession,
    settings: Settings,
    comp: CompetitionRef,
    year: int,
    from_dir: Path | None,
) -> FileResult:
    if from_dir is None:
        origin = f"{api_football.BASE_URL}/fixtures?league={comp.api_football_id}&season={year}"
        content, fixtures, notes = await _download_api_football(session, settings, comp, year)
        name = f"{comp.api_football_id}/{year}-{datetime.now(UTC):%Y%m%dT%H%M%S}.json"
    else:
        # Disposition du collecteur : <dossier>/<id de ligue>/<saison>.json
        path = from_dir / str(comp.api_football_id) / f"{year}.json"
        if not path.exists():
            raise raw_store.SourceUnavailableError(f"{path} : fichier absent", transient=False)
        origin, content = str(path), path.read_bytes()
        fixtures, parse_issues = api_football.parse_collector_file(json.loads(content))
        notes = parse_issues.items
        name = f"{comp.api_football_id}/{year}.json"

    raw_id = await raw_store.archive(
        session, settings.raw_data_dir, DataSource.API_FOOTBALL, origin, name, content
    )
    resolver = await loader.TeamResolver.load(session)
    stats = await loader.load_api_football(session, comp.code, year, fixtures, raw_id, resolver)
    stats.issues[:0] = notes
    with_stats = sum(1 for f in fixtures if f.stats)
    return {
        "origin": origin,
        "parsed_matches": len(fixtures),
        "with_stats": with_stats,
        **stats.as_dict(),
    }


_HANDLERS: dict[
    DataSource,
    Callable[[AsyncSession, Settings, CompetitionRef, int, Path | None], Awaitable[FileResult]],
] = {
    DataSource.FOOTBALL_DATA: _football_data_file,
    DataSource.UNDERSTAT: _understat_file,
    DataSource.API_FOOTBALL: _api_football_file,
}


# Âge au-delà duquel une exécution encore « running » est considérée interrompue.
STALE_RUN_AGE = timedelta(hours=6)

# Pause entre deux téléchargements, pour ne pas surcharger les sources.
DOWNLOAD_PAUSE_SECONDS = 1.5
# Après ce nombre d'échecs consécutifs (réseau, blocage), la source est
# considérée injoignable : ses fichiers restants ne sont pas tentés.
MAX_CONSECUTIVE_FAILURES = 3

Progress = Callable[[str], None]


def _describe(entry: FileResult) -> str:
    if entry["status"] == "ok":
        return (
            f"ok — matchs +{entry['matches_inserted']} ~{entry['matches_updated']}, "
            f"cotes {entry['odds_upserted']}, stats {entry['advanced_stats_upserted']}, "
            f"anomalies {len(entry['issues'])}"
        )
    return f"{entry['status']} — {entry['error']}"


async def run_ingestion(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    requests: Sequence[IngestionRequest],
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Exécute les ingestions demandées puis les contrôles de qualité ; renvoie le rapport."""
    async with factory() as session, session.begin():
        # Une exécution arrêtée en cours de route (Ctrl+C, redémarrage) resterait
        # « running » pour toujours : elle est marquée « interrupted ».
        await session.execute(
            update(IngestionRun)
            .where(
                IngestionRun.status == "running",
                IngestionRun.started_at < datetime.now(UTC) - STALE_RUN_AGE,
            )
            .values(status="interrupted", finished_at=datetime.now(UTC))
        )
        await loader.sync_reference(session)
        run = IngestionRun(
            source="+".join(r.source.value for r in requests),
            status="running",
            parameters={
                "requests": [
                    {
                        "source": r.source.value,
                        "competitions": list(r.competitions),
                        "seasons": list(r.seasons),
                        "from_dir": str(r.from_dir) if r.from_dir else None,
                    }
                    for r in requests
                ]
            },
            report={},
        )
        session.add(run)
    run_id = run.id

    notify = progress or (lambda _message: None)
    _progress.set(notify)
    total = sum(len(r.competitions) * len(r.seasons) for r in requests)
    done = 0
    files: list[FileResult] = []
    for request in requests:
        handler = _HANDLERS[request.source]
        downloading = request.from_dir is None
        consecutive_failures = 0
        for code in request.competitions:
            comp = COMPETITIONS_BY_CODE[code]
            for year in request.seasons:
                done += 1
                entry: FileResult = {
                    "source": request.source.value,
                    "competition": code,
                    "season": year,
                }
                label = f"[{done}/{total}] {request.source.value} {code} {year}"
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    entry.update(
                        status="unavailable",
                        error=f"non tenté : source injoignable "
                        f"({MAX_CONSECUTIVE_FAILURES} échecs consécutifs)",
                    )
                    files.append(entry)
                    notify(f"{label} : {_describe(entry)}")
                    continue
                notify(f"{label} …")
                try:
                    async with factory() as session, session.begin():
                        entry.update(await handler(session, settings, comp, year, request.from_dir))
                    entry["status"] = "ok"
                except raw_store.SourceUnavailableError as exc:
                    entry.update(status="unavailable", error=str(exc))
                    if exc.transient:
                        consecutive_failures += 1
                except loader.PrerequisiteMissingError as exc:
                    entry.update(status="unavailable", error=str(exc))
                except loader.UnknownTeamsError as exc:
                    entry.update(status="rejected", error=str(exc))
                except Exception as exc:
                    logger.exception("ingestion_file_failed", extra=entry)
                    entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                logger.info(
                    "ingestion_file", extra={k: v for k, v in entry.items() if k != "issues"}
                )
                if entry["status"] != "unavailable":
                    consecutive_failures = 0
                files.append(entry)
                notify(f"{label} : {_describe(entry)}")
                if downloading:
                    await asyncio.sleep(DOWNLOAD_PAUSE_SECONDS)

    async with factory() as session, session.begin():
        quality = await run_quality_checks(session)
        statuses = {f["status"] for f in files}
        if statuses & {"failed", "rejected"}:
            status = "failed"
        elif quality["errors"]:
            status = "quality_errors"
        elif "unavailable" in statuses:
            # Un fichier manquant n'est jamais passé sous silence.
            status = "partial"
        else:
            status = "ok"
        report = {"files": files, "quality": quality}
        run_row = await session.get(IngestionRun, run_id)
        assert run_row is not None
        run_row.status = status
        run_row.finished_at = datetime.now(UTC)
        run_row.report = report
    return {"run_id": run_id, "status": status, **report}
