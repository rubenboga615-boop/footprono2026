"""Données du jour depuis API-Football : cotes des matchs à venir.

Les cotes sont relevées pour les bookmakers de ``Settings.odds_bookmakers``
(noms API-Football, retrouvés par ``/odds/bookmakers``). Un bookmaker absent
du service est signalé dans le rapport, jamais remplacé par un autre en silence.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.core.config import Settings
from footprono.football.models import BookmakerOdds, DataSource, Match
from footprono.ingestion import raw_store, service
from footprono.ingestion.quality import current_season_start
from footprono.ingestion.reference import COMPETITIONS
from footprono.ingestion.sources import api_football
from footprono.ingestion.sources.api_football_odds import OddsQuote, map_bet, parse_odds_page

MAX_PAGES = 10  # sécurité : 10 matchs par page, une journée en tient deux au plus


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
    unmapped = sorted({q.bet for q in quotes if map_bet(q.bet, q.value) is None})
    report.update(
        matches=len(matches),
        quotes=len(quotes),
        changed=added,
        unmapped_bets=unmapped,
    )
    return report


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
