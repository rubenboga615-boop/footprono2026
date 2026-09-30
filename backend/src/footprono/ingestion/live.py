"""Données du jour depuis API-Football : cotes des matchs à venir, suivi en direct.

Cotes : relevées pour les bookmakers de ``Settings.odds_bookmakers`` (noms
API-Football, retrouvés par ``/odds/bookmakers``). Un bookmaker absent du
service est signalé dans le rapport, jamais remplacé par un autre en silence.

Direct (``follow_live``) : pendant les matchs, minute et score ; dès la fin,
score final et mi-temps (provisoires, ``result_source = api_football``) puis
statistiques par période. football-data confirme le lendemain et remplace le
score s'il diffère (écart signalé par le chargement football-data).
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.core.config import Settings
from footprono.football.models import (
    BookmakerOdds,
    DataSource,
    Match,
    MatchStatus,
    MatchTeamSheet,
    MatchTeamStats,
    StatPeriod,
)
from footprono.ingestion import raw_store, service
from footprono.ingestion.quality import current_season_start
from footprono.ingestion.reference import COMPETITIONS
from footprono.ingestion.sources import api_football
from footprono.ingestion.sources.api_football_odds import OddsQuote, map_bet, parse_odds_page
from footprono.ingestion.sources.common import ParseIssues

MAX_PAGES = 10  # sécurité : 10 matchs par page, une journée en tient deux au plus

# Fenêtre de suivi : du coup d'envoi (moins une marge) à 3 h 30 après.
LIVE_BEFORE = timedelta(minutes=5)
LIVE_AFTER = timedelta(hours=3, minutes=30)
# Statistiques encore absentes à la fin : redemandées jusqu'à 8 h après le coup d'envoi.
STATS_RETRY_UNTIL = timedelta(hours=8)
IDS_PER_REQUEST = 20  # limite de /fixtures?ids=
LINEUPS_BEFORE = timedelta(minutes=75)
# Statuts API-Football d'un match en cours (mi-temps et interruptions comprises).
LIVE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "SUSP", "INT"})


def _noop(_message: str) -> None:
    return None


async def _bookmaker_ids(
    client: api_football.ApiFootballClient, wanted: list[str]
) -> tuple[dict[str, int], list[str]]:
    body = await client.get("/odds/bookmakers", {})
    available = {str(b["name"]).lower(): (str(b["name"]), int(b["id"])) for b in body["response"]}
    found: dict[str, int] = {}
    missing: list[str] = []
    for name in wanted:
        hit = available.get(name.lower())
        if hit is None:
            missing.append(name)
        else:
            found[hit[0]] = hit[1]
    return found, missing


async def collect_odds(
    session: AsyncSession,
    settings: Settings,
    progress: Callable[[str], None] = _noop,
) -> dict[str, Any]:
    """Relève les cotes des matchs à venir et enregistre celles qui ont changé."""
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}
    season = current_season_start()
    fetched_at = datetime.now(UTC)
    quotes: list[OddsQuote] = []
    pages: list[dict[str, Any]] = []
    report: dict[str, Any] = {"status": "ok", "issues": [], "bookmakers": {}}
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=settings.api_football_budget,
        min_remaining=settings.api_football_min_remaining,
        transport=service.api_football_transport,
    ) as client:
        await client.status()
        books, missing = await _bookmaker_ids(client, settings.odds_bookmakers)
        for name in missing:
            report["issues"].append(f"bookmaker « {name} » absent d'API-Football : non relevé")
        for comp in COMPETITIONS:
            for name, book_id in books.items():
                page, total = 1, 1
                while page <= min(total, MAX_PAGES):
                    if not client.can_spend():
                        report["status"] = "partial"
                        report["issues"].append("quota API-Football atteint : relevé incomplet")
                        break
                    body = await client.get(
                        "/odds",
                        {
                            "league": comp.api_football_id,
                            "season": season,
                            "bookmaker": book_id,
                            "page": page,
                        },
                    )
                    pages.append(body)
                    found, _, total = parse_odds_page(body)
                    quotes.extend(found)
                    page += 1
                progress(f"{comp.code} {name} : {len(quotes)} cotes relevées au total")
        report["requests"] = client.used

    by_fixture = {q.fixture_id for q in quotes}
    rows = await session.execute(
        select(Match.api_football_id, Match.id).where(Match.api_football_id.in_(by_fixture))
    )
    matches: dict[int, int] = {int(f): m for f, m in rows.tuples() if f is not None}
    unknown = by_fixture - set(matches)
    if unknown:
        report["issues"].append(f"{len(unknown)} matchs API-Football inconnus en base : ignorés")

    raw_id = None
    if pages:
        raw_id = await raw_store.archive(
            session,
            settings.raw_data_dir,
            DataSource.API_FOOTBALL,
            f"{api_football.BASE_URL}/odds",
            f"odds/{fetched_at:%Y%m%dT%H%M%S}.json",
            json.dumps(pages).encode(),
        )
    latest = await _latest_prices(session, list(matches.values()))
    added = 0
    for q in quotes:
        match_id = matches.get(q.fixture_id)
        if match_id is None:
            continue
        key = (match_id, q.bookmaker, q.bet, q.value)
        if latest.get(key) == q.price:
            continue
        latest[key] = q.price
        session.add(
            BookmakerOdds(
                match_id=match_id,
                fetched_at=fetched_at,
                source_updated_at=q.updated_at,
                bookmaker=q.bookmaker,
                bet=q.bet,
                value=q.value,
                price=q.price,
                raw_file_id=raw_id,
            )
        )
        added += 1
        report["bookmakers"][q.bookmaker] = report["bookmakers"].get(q.bookmaker, 0) + 1
    await session.commit()
    # Paris dont au moins une sélection n'est pas traduite, avec quelques libellés
    # réels (pour compléter la traduction) et s'ils sont traduits en partie.
    values: dict[str, set[str]] = {}
    mapped: set[str] = set()
    for q in quotes:
        if map_bet(q.bet, q.value) is None:
            values.setdefault(q.bet, set()).add(q.value)
        else:
            mapped.add(q.bet)
    unmapped = {
        bet: {"partial": bet in mapped, "values": sorted(v)[:12]}
        for bet, v in sorted(values.items())
    }
    report.update(
        matches=len(matches),
        quotes=len(quotes),
        changed=added,
        unmapped_bets=unmapped,
    )
    return report


async def follow_live(
    session: AsyncSession,
    settings: Settings,
    now: datetime | None = None,
    progress: Callable[[str], None] = _noop,
) -> dict[str, Any]:
    """Met à jour les matchs en cours ; termine ceux qui sont finis, avec leurs statistiques.

    Sans match dans sa fenêtre, ne fait aucune requête (appelable toutes les
    2 minutes).
    """
    now = now or datetime.now(UTC)
    has_stats = (
        select(MatchTeamStats.id)
        .where(
            MatchTeamStats.match_id == Match.id,
            MatchTeamStats.source == DataSource.API_FOOTBALL,
            MatchTeamStats.period == StatPeriod.FULL,
        )
        .exists()
    )
    has_lineups = (
        select(MatchTeamSheet.id)
        .where(MatchTeamSheet.match_id == Match.id, MatchTeamSheet.kind == "lineups")
        .exists()
    )
    windows = [
        (Match.status == MatchStatus.SCHEDULED)
        & Match.kickoff_at.between(now - LIVE_AFTER, now + LIVE_BEFORE),
        (Match.status == MatchStatus.FINISHED)
        & (Match.result_source == "api_football")
        & (Match.kickoff_at >= now - STATS_RETRY_UNTIL)
        & ~has_stats,
    ]
    if now.minute % 10 < 2:
        # Compositions publiées ~1 h avant : matchs de l'heure qui vient, un passage
        # sur cinq (toutes les 10 minutes) tant qu'elles manquent.
        windows.append(
            (Match.status == MatchStatus.SCHEDULED)
            & Match.kickoff_at.between(now, now + LINEUPS_BEFORE)
            & ~has_lineups
        )
    candidates = list(
        (
            await session.scalars(
                select(Match).where(Match.api_football_id.is_not(None), or_(*windows))
            )
        ).all()
    )
    if not candidates:
        return {"status": "idle", "requests": 0}
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}

    by_fixture = {int(m.api_football_id): m for m in candidates if m.api_football_id is not None}
    report: dict[str, Any] = {"status": "ok", "live": 0, "finished": [], "stats": 0, "issues": []}
    items: list[dict[str, Any]] = []
    statistics: dict[int, list[dict[str, Any]]] = {}
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=settings.api_football_budget,
        min_remaining=settings.api_football_min_remaining,
        transport=service.api_football_transport,
    ) as client:
        await client.status()
        ids = sorted(by_fixture)
        for start in range(0, len(ids), IDS_PER_REQUEST):
            chunk = ids[start : start + IDS_PER_REQUEST]
            body = await client.get("/fixtures", {"ids": "-".join(map(str, chunk))})
            items.extend(body["response"])
        for item in items:
            fixture = api_football.parse_fixture(item)
            match = by_fixture.get(fixture.fixture_id)
            if match is None or not fixture.finished:
                continue
            if not client.can_spend():
                report["issues"].append("quota atteint : statistiques redemandées plus tard")
                break
            body = await client.get(
                "/fixtures/statistics", {"fixture": fixture.fixture_id, "half": "true"}
            )
            statistics[fixture.fixture_id] = body["response"]
        report["requests"] = client.used

    raw_id = await raw_store.archive(
        session,
        settings.raw_data_dir,
        DataSource.API_FOOTBALL,
        f"{api_football.BASE_URL}/fixtures?ids=",
        f"live/{now:%Y%m%dT%H%M%S}.json",
        json.dumps({"fixtures": items, "statistics": statistics}).encode(),
    )
    for item in items:
        fixture = api_football.parse_fixture(item)
        match = by_fixture.get(fixture.fixture_id)
        if match is None:
            continue
        label = f"{fixture.home_team}-{fixture.away_team}"
        lineups = item.get("lineups")
        if isinstance(lineups, list) and lineups:
            await save_team_sheet(session, match.id, "lineups", lineups, now)
            report["lineups"] = report.get("lineups", 0) + 1
        if match.status is MatchStatus.SCHEDULED:
            values: dict[str, Any] = {"api_status": fixture.status, "live_updated_at": now}
            if fixture.status in LIVE_STATUSES or fixture.finished:
                values.update(
                    live_minute=item["fixture"]["status"].get("elapsed"),
                    live_home_goals=fixture.home_goals,
                    live_away_goals=fixture.away_goals,
                )
                report["live"] += 0 if fixture.finished else 1
            if (
                fixture.finished
                and fixture.home_goals is not None
                and fixture.away_goals is not None
            ):
                values.update(
                    status=MatchStatus.FINISHED,
                    home_goals=fixture.home_goals,
                    away_goals=fixture.away_goals,
                    home_goals_ht=fixture.home_goals_ht,
                    away_goals_ht=fixture.away_goals_ht,
                    result_source="api_football",
                )
                report["finished"].append(f"{label} {fixture.home_goals}-{fixture.away_goals}")
                progress(f"terminé : {label} {fixture.home_goals}-{fixture.away_goals}")
            await session.execute(update(Match).where(Match.id == match.id).values(**values))
        response = statistics.get(fixture.fixture_id)
        if response is None:
            continue
        issues = ParseIssues()
        periods = api_football.parse_statistics(response, item["teams"]["home"]["id"], issues)
        report["issues"].extend(issues.items)
        if not periods:
            report["issues"].append(f"{label} : statistiques pas encore publiées")
            continue
        rows = [
            {
                "match_id": match.id,
                "team_id": team_id,
                "source": DataSource.API_FOOTBALL,
                "period": period,
                "raw_file_id": raw_id,
                **values_,
            }
            for period, (home_stats, away_stats) in periods.items()
            for team_id, values_ in (
                (match.home_team_id, home_stats),
                (match.away_team_id, away_stats),
            )
        ]
        stmt = insert(MatchTeamStats).values(rows)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["match_id", "team_id", "source", "period"],
                set_={
                    k: stmt.excluded[k]
                    for k in rows[0]
                    if k not in ("match_id", "team_id", "source", "period")
                },
            )
        )
        report["stats"] += 1
    await session.commit()
    return report


async def save_team_sheet(
    session: AsyncSession, match_id: int, kind: str, payload: list[Any], fetched_at: datetime
) -> None:
    """Enregistre la dernière version (compositions ou blessés) d'un match."""
    stmt = insert(MatchTeamSheet).values(
        match_id=match_id, kind=kind, payload=payload, fetched_at=fetched_at
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["match_id", "kind"],
            set_={"payload": stmt.excluded.payload, "fetched_at": stmt.excluded.fetched_at},
        )
    )


async def collect_injuries(
    session: AsyncSession, settings: Settings, today: datetime | None = None
) -> dict[str, Any]:
    """Blessés et suspendus des matchs d'aujourd'hui et de demain (1 requête par
    championnat et par jour), rattachés aux matchs par leur identifiant API-Football."""
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}
    now = today or datetime.now(UTC)
    season = current_season_start()
    by_fixture: dict[int, list[Any]] = {}
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=settings.api_football_budget,
        min_remaining=settings.api_football_min_remaining,
        transport=service.api_football_transport,
    ) as client:
        await client.status()
        for comp in COMPETITIONS:
            for day in (now.date(), now.date() + timedelta(days=1)):
                if not client.can_spend():
                    break
                body = await client.get(
                    "/injuries",
                    {"league": comp.api_football_id, "season": season, "date": day.isoformat()},
                )
                for entry in body["response"]:
                    fixture_id = (entry.get("fixture") or {}).get("id")
                    if fixture_id is not None:
                        by_fixture.setdefault(int(fixture_id), []).append(entry)
        used = client.used
    rows = await session.execute(
        select(Match.api_football_id, Match.id).where(Match.api_football_id.in_(by_fixture))
    )
    matches = {int(f): m for f, m in rows.tuples() if f is not None}
    for fixture_id, entries in by_fixture.items():
        if fixture_id in matches:
            await save_team_sheet(session, matches[fixture_id], "injuries", entries, now)
    await session.commit()
    return {
        "status": "ok",
        "requests": used,
        "matches": len(set(by_fixture) & set(matches)),
        "unknown_fixtures": len(set(by_fixture) - set(matches)),
    }


async def _latest_prices(
    session: AsyncSession, match_ids: list[int]
) -> dict[tuple[int, str, str, str], Decimal]:
    """Dernière cote enregistrée par (match, bookmaker, pari, sélection)."""
    if not match_ids:
        return {}
    last = (
        select(
            BookmakerOdds.match_id,
            BookmakerOdds.bookmaker,
            BookmakerOdds.bet,
            BookmakerOdds.value,
            func.max(BookmakerOdds.id).label("id"),
        )
        .where(BookmakerOdds.match_id.in_(match_ids))
        .group_by(
            BookmakerOdds.match_id, BookmakerOdds.bookmaker, BookmakerOdds.bet, BookmakerOdds.value
        )
        .subquery()
    )
    rows = await session.execute(
        select(
            BookmakerOdds.match_id,
            BookmakerOdds.bookmaker,
            BookmakerOdds.bet,
            BookmakerOdds.value,
            BookmakerOdds.price,
        ).join(last, last.c.id == BookmakerOdds.id)
    )
    return {(m, b, bet, v): p for m, b, bet, v, p in rows.tuples()}
