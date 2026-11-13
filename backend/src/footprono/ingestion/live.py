"""Données du jour depuis API-Football : cotes des matchs à venir, suivi en direct.

Cotes : relevées pour les bookmakers de ``Settings.odds_bookmakers`` (noms
API-Football, retrouvés par ``/odds/bookmakers``). Un bookmaker absent du
service est signalé dans le rapport, jamais remplacé par un autre en silence.

Direct (``follow_live``) : pendant les matchs, minute et score ; dès la fin,
score final et mi-temps (provisoires, ``result_source = api_football``) puis
statistiques par période. football-data confirme le lendemain et remplace le
score s'il diffère (écart signalé par le chargement football-data).
"""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker import live_coupons
from footprono.core.config import Settings
from footprono.football import logos
from footprono.football.models import (
    BookmakerOdds,
    Competition,
    DataSource,
    LiveSnapshot,
    Match,
    MatchStatus,
    MatchTeamSheet,
    MatchTeamStats,
    RawFile,
    Season,
    StatPeriod,
)
from footprono.ingestion import details, loader, raw_store, service
from footprono.ingestion.reference import (
    COMPETITIONS,
    COMPETITIONS_BY_CODE,
    CUPS,
    NATIONS,
    cup_season,
    current_season,
)
from footprono.ingestion.sources import api_football
from footprono.ingestion.sources.api_football_odds import (
    OddsQuote,
    handicap_diagnostics,
    map_bet,
    parse_odds_page,
)
from footprono.ingestion.sources.common import ParseIssues

MAX_PAGES = 10  # sécurité : 10 matchs par page, une journée en tient deux au plus

# Fenêtre de suivi : du coup d'envoi (moins une marge) à 3 h 30 après.
LIVE_BEFORE = timedelta(minutes=5)
LIVE_AFTER = timedelta(hours=3, minutes=30)
# Statistiques encore absentes à la fin : redemandées jusqu'à 8 h après le coup d'envoi.
STATS_RETRY_UNTIL = timedelta(hours=8)
IDS_PER_REQUEST = 20  # limite de /fixtures?ids=
LINEUPS_BEFORE = timedelta(minutes=75)
# Relevé chaque minute (retour du fondateur du 12/11/2026) : les minutes impaires ne suivent
# que les matchs en cours, et seulement s'il reste au moins cette marge de requêtes du jour
# au-dessus de la réserve ; sinon le suivi revient de lui-même à toutes les 2 minutes.
EVERY_MINUTE_MARGIN = 1000
# Statuts API-Football d'un match en cours (mi-temps et interruptions comprises).
LIVE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "SUSP", "INT"})
# Statuts où le score de la 1re mi-temps est définitif.
HALF_TIME_KNOWN = frozenset({"HT", "2H", "ET", "BT", "P"})


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


async def _nation_targets(session: AsyncSession, now: datetime) -> list[tuple[str, int, int]]:
    official = [n.code for n in NATIONS if n.official]
    rows = await session.execute(
        select(Competition.code, Competition.api_football_id, Season.start_year)
        .join(Season, Season.competition_id == Competition.id)
        .join(Match, Match.season_id == Season.id)
        .where(
            Competition.code.in_(official),
            Match.status == MatchStatus.SCHEDULED,
            Match.kickoff_at.between(now, now + timedelta(days=14)),
        )
        .distinct()
    )
    return [
        (code, int(api_id), int(year)) for code, api_id, year in rows.tuples() if api_id is not None
    ]


async def collect_odds(
    session: AsyncSession,
    settings: Settings,
    progress: Callable[[str], None] = _noop,
) -> dict[str, Any]:
    """Relève les cotes des matchs à venir et enregistre celles qui ont changé."""
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}
    # Saison en cours par championnat (année civile en Norvège et en Suède).
    seasons = {comp.code: current_season(comp) for comp in COMPETITIONS}
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
        # Calendrier de la saison (1 requête par championnat) : relie les matchs à
        # venir à leur identifiant API-Football avant d'y rattacher les cotes.
        calendars = {
            comp.code: await client.get(
                "/fixtures", {"league": comp.api_football_id, "season": seasons[comp.code]}
            )
            for comp in COMPETITIONS
        }
        books, missing = await _bookmaker_ids(client, settings.odds_bookmakers)
        for name in missing:
            report["issues"].append(f"bookmaker « {name} » absent d'API-Football : non relevé")
        # Coupes d'Europe aussi (saison de juillet à juin) : leurs matchs sont en base par
        # l'import des coupes ; cotes gardées pour comparer plus tard le moteur au marché.
        targets = [(c.code, c.api_football_id, seasons[c.code]) for c in COMPETITIONS] + [
            (c.code, c.api_football_id, cup_season(fetched_at.date())) for c in CUPS
        ]
        # Sélections : les saisons qui ont un match officiel dans les 14 jours (pas de règle
        # de saison commune) ; aucune requête hors des fenêtres internationales.
        targets += await _nation_targets(session, fetched_at)
        for code, league_id, season in targets:
            for name, book_id in books.items():
                page, total = 1, 1
                while page <= min(total, MAX_PAGES):
                    if not client.can_spend():
                        report["status"] = "partial"
                        report["issues"].append("quota API-Football atteint : relevé incomplet")
                        break
                    body = await client.get(
                        "/odds",
                        {"league": league_id, "season": season, "bookmaker": book_id, "page": page},
                    )
                    pages.append(body)
                    found, _, total = parse_odds_page(body)
                    quotes.extend(found)
                    page += 1
                progress(f"{code} {name} : {len(quotes)} cotes relevées au total")
        report["requests"] = client.used

    report["calendar"] = await _sync_calendars(session, settings, seasons, calendars, fetched_at)
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
    still_offered: list[int] = []
    # Date de mise à jour annoncée par la source pour les cotes inchangées : la source
    # peut confirmer un prix sans le changer, la date affichée doit le refléter.
    confirmed: dict[datetime, list[int]] = {}
    for q in quotes:
        match_id = matches.get(q.fixture_id)
        if match_id is None:
            continue
        key = (match_id, q.bookmaker, q.bet, q.value)
        previous = latest.get(key)
        if previous is not None and previous[1] == q.price:
            still_offered.append(previous[0])  # inchangée : seulement « vue » à nouveau
            if q.updated_at is not None and previous[0]:
                confirmed.setdefault(q.updated_at, []).append(previous[0])
            continue
        latest[key] = (0, q.price)
        session.add(
            BookmakerOdds(
                match_id=match_id,
                fetched_at=fetched_at,
                last_seen_at=fetched_at,
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
    for start in range(0, len(still_offered), 5000):
        await session.execute(
            update(BookmakerOdds)
            .where(BookmakerOdds.id.in_(still_offered[start : start + 5000]))
            .values(last_seen_at=fetched_at)
        )
    for updated, ids in confirmed.items():
        for start in range(0, len(ids), 5000):
            await session.execute(
                update(BookmakerOdds)
                .where(
                    BookmakerOdds.id.in_(ids[start : start + 5000]),
                    BookmakerOdds.source_updated_at.is_distinct_from(updated),
                )
                .values(source_updated_at=updated)
            )
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
    report["handicap_check"] = handicap_diagnostics(quotes)
    report.update(
        matches=len(matches),
        quotes=len(quotes),
        changed=added,
        unmapped_bets=unmapped,
    )
    return report


async def _sync_calendars(
    session: AsyncSession,
    settings: Settings,
    seasons: dict[str, int],
    calendars: dict[str, dict[str, Any]],
    fetched_at: datetime,
) -> dict[str, Any]:
    """Charge le calendrier de chaque championnat (identifiants, heures, statuts, arbitres)."""
    resolver = await loader.TeamResolver.load(session)
    out: dict[str, Any] = {}
    for code, body in calendars.items():
        comp = COMPETITIONS_BY_CODE[code]
        season = seasons[code]
        fixtures = [
            api_football.parse_fixture(i)
            for i in body["response"]
            if api_football.is_league_match(i, comp.playoffs)
        ]
        raw_id = await raw_store.archive(
            session,
            settings.raw_data_dir,
            DataSource.API_FOOTBALL,
            f"{api_football.BASE_URL}/fixtures?league={comp.api_football_id}&season={season}",
            f"{comp.api_football_id}/calendar-{fetched_at:%Y%m%dT%H%M%S}.json",
            json.dumps(body).encode(),
        )
        try:
            stats = await loader.load_api_football(
                session, code, season, fixtures, raw_id, resolver
            )
        except (loader.PrerequisiteMissingError, loader.UnknownTeamsError) as exc:
            out[code] = {"error": str(exc)}
            continue
        out[code] = {"updated": stats.matches_updated, "issues": stats.issues}
    await session.commit()
    return out


def regulation_score(item: dict[str, Any]) -> tuple[int | None, int | None]:
    """Score du temps réglementaire, celui des paris : après une prolongation (« AET ») ou
    des tirs au but (« PEN »), ``goals`` compte la prolongation ; ``score.fulltime`` non."""
    status = (item.get("fixture") or {}).get("status", {}).get("short")
    if status in ("AET", "PEN"):
        full = (item.get("score") or {}).get("fulltime") or {}
        return full.get("home"), full.get("away")
    goals = item.get("goals") or {}
    return goals.get("home"), goals.get("away")


async def follow_live(
    session: AsyncSession,
    settings: Settings,
    now: datetime | None = None,
    progress: Callable[[str], None] = _noop,
) -> dict[str, Any]:
    """Met à jour les matchs en cours ; termine ceux qui sont finis, avec leurs statistiques.

    Sans match dans sa fenêtre, ne fait aucune requête. Appelé chaque minute : les minutes
    paires font tout (matchs en cours, statistiques, compositions), les minutes impaires
    seulement les matchs en cours, si le quota du jour le permet (``EVERY_MINUTE_MARGIN``).
    """
    now = now or datetime.now(UTC)
    extra_pass = now.minute % 2 == 1
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
    ]
    if not extra_pass:
        windows.append(
            (Match.status == MatchStatus.FINISHED)
            & (Match.result_source == "api_football")
            & (Match.kickoff_at >= now - STATS_RETRY_UNTIL)
            & ~has_stats
        )
    if now.minute % 10 == 0:
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
        reserve = settings.api_football_min_remaining + EVERY_MINUTE_MARGIN
        if extra_pass and client.day_remaining is not None and client.day_remaining < reserve:
            return {"status": "idle", "requests": 0, "skipped": "quota : relevé toutes les 2 min"}
        ids = sorted(by_fixture)
        for start in range(0, len(ids), IDS_PER_REQUEST):
            chunk = ids[start : start + IDS_PER_REQUEST]
            body = await client.get("/fixtures", {"ids": "-".join(map(str, chunk))})
            items.extend(body["response"])
        # Coupon en direct (13/11/2026) : cotes en direct de tous les matchs en cours, une
        # requête, seulement quand un match suivi est dans une fenêtre et le coupon publié.
        wanted = {
            int(it["fixture"]["id"])
            for it in items
            if live_coupons.odds_wanted(
                it["fixture"]["status"].get("short"), it["fixture"]["status"].get("elapsed")
            )
        } & set(by_fixture)
        if wanted and client.can_spend() and (await live_coupons.settings_of(session))[0]:
            odds_body = await client.get("/odds/live", {})
            # Score du relevé des matchs : des cotes d'un autre score (relevées avant un but)
            # ou suspendues par la source ne sont pas gardées.
            scores = {
                int(it["fixture"]["id"]): [(it.get("goals") or {}).get(s) for s in ("home", "away")]
                for it in items
            }
            report["live_odds"] = {
                by_fixture[fid].id: {
                    "at": now.isoformat(),
                    "update": entry.get("update"),
                    "odds": live_coupons.parse_live_odds(entry),
                }
                for entry in odds_body.get("response") or []
                if (fid := int((entry.get("fixture") or {}).get("id") or 0)) in wanted
                and live_coupons.entry_current(entry, scores.get(fid))
            }
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
        # Numéros des équipes chez API-Football : logos (football/logos.py).
        await logos.remember_api_ids(
            session, [(match.home_team_id, fixture.home_id), (match.away_team_id, fixture.away_id)]
        )
        label = f"{fixture.home_team}-{fixture.away_team}"
        lineups = item.get("lineups")
        if isinstance(lineups, list) and lineups:
            await save_team_sheet(session, match.id, "lineups", lineups, now)
            report["lineups"] = report.get("lineups", 0) + 1
        # Événements, relevé (minute, score, statistiques), compositions et joueurs rangés
        # à chaque passage : même réponse, aucune requête en plus (plan du 10/11/2026).
        stored = await details.store(session, match.id, item, now, raw_id)
        report["events"] = report.get("events", 0) + stored.events
        report["snapshots"] = report.get("snapshots", 0) + stored.snapshots
        if match.status is MatchStatus.SCHEDULED:
            values: dict[str, Any] = {"api_status": fixture.status, "live_updated_at": now}
            # Coup d'envoi retardé ou avancé : repris à chaque passage (avant : à la collecte
            # des cotes suivante, jusqu'à 3 h plus tard ; essai réel du 06/11/2026, un match
            # affiché « à venir 18:00 » alors qu'il commençait vers 18 h 45).
            if fixture.kickoff is not None and fixture.kickoff != match.kickoff_at:
                values.update(kickoff_at=fixture.kickoff, match_date=fixture.kickoff.date())
                # Nouvelle heure poussée aussi à l'application (retour du 12/11/2026).
                report.setdefault("updated", []).append(match.id)
            if fixture.status in LIVE_STATUSES or fixture.finished:
                values.update(
                    live_minute=item["fixture"]["status"].get("elapsed"),
                    # Temps additionnel (« 90+4 ») : absent ou nul le reste du match.
                    live_extra=item["fixture"]["status"].get("extra") or None,
                    live_home_goals=fixture.home_goals,
                    live_away_goals=fixture.away_goals,
                )
                # Score de la mi-temps dès la pause (avant : seulement à la fin du match, et
                # les paris sur la 1re mi-temps attendaient le coup de sifflet final).
                if fixture.status in HALF_TIME_KNOWN and fixture.home_goals_ht is not None:
                    values.update(
                        home_goals_ht=fixture.home_goals_ht, away_goals_ht=fixture.away_goals_ht
                    )
                report["live"] += 0 if fixture.finished else 1
                # Matchs à pousser à l'application ouverte (notifications/live_feed.py).
                report.setdefault("updated", []).append(match.id)
            home_goals, away_goals = regulation_score(item)
            if fixture.finished and home_goals is not None and away_goals is not None:
                values.update(
                    status=MatchStatus.FINISHED,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    home_goals_ht=fixture.home_goals_ht,
                    away_goals_ht=fixture.away_goals_ht,
                    result_source="api_football",
                )
                report["finished"].append(f"{label} {home_goals}-{away_goals}")
                progress(f"terminé : {label} {home_goals}-{away_goals}")
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
                    {
                        "league": comp.api_football_id,
                        "season": current_season(comp, now.date()),
                        "date": day.isoformat(),
                    },
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
) -> dict[tuple[int, str, str, str], tuple[int, Decimal]]:
    """Dernière cote enregistrée (identifiant, prix) par (match, bookmaker, pari, sélection)."""
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
            BookmakerOdds.id,
            BookmakerOdds.price,
        ).join(last, last.c.id == BookmakerOdds.id)
    )
    return {(m, b, bet, v): (i, p) for m, b, bet, v, i, p in rows.tuples()}


# --- Données du direct : relecture, rattrapage, essai (plan du 10/11/2026, étape 1) ---

LIVE_ORIGIN = f"{api_football.BASE_URL}/fixtures?ids="


async def replay_live_files(
    session: AsyncSession, progress: Callable[[str], None] = _noop
) -> dict[str, Any]:
    """Range les relevés déjà gardés sur le disque (réponses du suivi en direct), dans
    l'ordre où ils ont été pris. Aucune requête."""
    files = (
        await session.scalars(
            select(RawFile).where(RawFile.origin == LIVE_ORIGIN).order_by(RawFile.fetched_at)
        )
    ).all()
    ids = {
        a: m
        for a, m in (
            await session.execute(
                select(Match.api_football_id, Match.id).where(Match.api_football_id.is_not(None))
            )
        ).tuples()
        if a is not None
    }
    total = details.Stored()
    missing = read = 0
    for raw in files:
        try:
            data = json.loads(await asyncio.to_thread(Path(raw.path).read_bytes))
        except (OSError, ValueError):
            missing += 1
            continue
        read += 1
        for item in data.get("fixtures") or []:
            match_id = ids.get(int(item.get("fixture", {}).get("id") or 0))
            if match_id is not None:
                total.add(await details.store(session, match_id, item, raw.fetched_at, raw.id))
        await session.commit()
        if read % 50 == 0:
            progress(f"{read} fichiers relus sur {len(files)}")
    return {
        "files": len(files),
        "read": read,
        "missing": missing,
        "stored": total.summary(),
        "stat_types": sorted(total.stat_types),
    }


async def backfill_details(
    session: AsyncSession,
    settings: Settings,
    *,
    competition: str | None = None,
    max_requests: int = 100,
    progress: Callable[[str], None] = _noop,
) -> dict[str, Any]:
    """Événements, compositions, statistiques d'équipes et de joueurs des matchs terminés
    qui n'en ont pas encore, les plus récents d'abord, 20 matchs par requête."""
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}
    done = select(LiveSnapshot.id).where(LiveSnapshot.match_id == Match.id).exists()

    def missing(query: Any) -> Any:
        query = query.where(
            Match.status == MatchStatus.FINISHED, Match.api_football_id.is_not(None), ~done
        )
        if competition:
            query = (
                query.join(Season, Season.id == Match.season_id)
                .join(Competition, Competition.id == Season.competition_id)
                .where(Competition.code == competition)
            )
        return query

    query = (
        missing(select(Match.api_football_id, Match.id))
        .order_by(Match.kickoff_at.desc().nulls_last(), Match.match_date.desc())
        .limit(max_requests * IDS_PER_REQUEST)
    )
    todo = {a: m for a, m in (await session.execute(query)).tuples() if a is not None}
    report: dict[str, Any] = {
        "status": "ok", "matches": 0, "requests": 0, "empty": 0, "not_returned": 0,
    }  # fmt: skip
    total = details.Stored()
    now = datetime.now(UTC)
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=max_requests,
        min_remaining=settings.api_football_min_remaining,
        transport=service.api_football_transport,
    ) as client:
        await client.status()
        ids = list(todo)
        for start in range(0, len(ids), IDS_PER_REQUEST):
            if not client.can_spend():
                report["stopped"] = "quota ou limite de requêtes atteinte"
                break
            chunk = ids[start : start + IDS_PER_REQUEST]
            body = await client.get("/fixtures", {"ids": "-".join(map(str, chunk))})
            items = body.get("response") or []
            raw_id = await raw_store.archive(
                session,
                settings.raw_data_dir,
                DataSource.API_FOOTBALL,
                LIVE_ORIGIN,
                f"details/{now:%Y%m%dT%H%M%S}-{start // IDS_PER_REQUEST}.json",
                json.dumps({"fixtures": items}).encode(),
            )
            returned = {int(item.get("fixture", {}).get("id") or 0) for item in items}
            report["not_returned"] += len(set(chunk) - returned)
            for item in items:
                match_id = todo.get(int(item.get("fixture", {}).get("id") or 0))
                if match_id is None:
                    continue
                stored = await details.store(session, match_id, item, now, raw_id)
                report["matches"] += 1
                report["empty"] += int(stored.events == 0 and stored.lineups == 0)
                total.add(stored)
            await session.commit()
            progress(f"{report['matches']} matchs complétés ({client.used} requêtes)")
        report["requests"] = client.used
    # Ce qui reste en tout (pas seulement dans ce lot) : 0 = tout est complet.
    report["left"] = int(
        await session.scalar(missing(select(func.count()).select_from(Match))) or 0
    )
    report["stored"] = total.summary()
    report["stat_types"] = sorted(total.stat_types)
    return report


async def probe_live(
    session: AsyncSession, settings: Settings, fixture_id: int | None = None
) -> dict[str, Any]:
    """Essai : ce que renvoient ``/fixtures?ids=`` et ``/odds/live`` pour un match en cours
    (ou le dernier match suivi). Deux requêtes, rien d'enregistré."""
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}
    if fixture_id is None:
        playing = await session.scalar(
            select(Match.api_football_id)
            .where(Match.api_football_id.is_not(None), Match.api_status.in_(LIVE_STATUSES))
            .order_by(Match.kickoff_at.desc())
            .limit(1)
        )
        recent = await session.scalar(
            select(Match.api_football_id)
            .where(Match.api_football_id.is_not(None), Match.status == MatchStatus.FINISHED)
            .order_by(Match.kickoff_at.desc().nulls_last())
            .limit(1)
        )
        fixture_id = int(playing or recent or 0) or None
    if fixture_id is None:
        return {"status": "idle", "error": "aucun match suivi"}
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=2,
        min_remaining=settings.api_football_min_remaining,
        transport=service.api_football_transport,
    ) as client:
        body = await client.get("/fixtures", {"ids": str(fixture_id)})
        odds = await client.get("/odds/live", {"fixture": fixture_id})
    items = body.get("response") or []
    out: dict[str, Any] = {"status": "ok", "fixture": fixture_id, "found": bool(items)}
    if items:
        item = items[0]
        home, away = details.team_stats(item)
        out.update(
            match=f"{item['teams']['home']['name']} - {item['teams']['away']['name']}",
            state=item["fixture"]["status"].get("short"),
            minute=item["fixture"]["status"].get("elapsed"),
            # Score de la source et minute de chaque but des événements (12/11/2026 : 1-1
            # selon les cotes, un seul but dans les événements).
            score="-".join(str((item.get("goals") or {}).get(k)) for k in ("home", "away")),
            goal_minutes=[
                f"{(e.get('time') or {}).get('elapsed')}' {(e.get('team') or {}).get('name')}"
                for e in item.get("events") or []
                if e.get("type") == "Goal"
            ],
            blocks=sorted(k for k, v in item.items() if v),
            events=len(item.get("events") or []),
            event_kinds=sorted({str(e.get("type")) for e in item.get("events") or []}),
            lineups=len(item.get("lineups") or []),
            players=sum(len(b.get("players") or []) for b in item.get("players") or []),
            stat_types=sorted(set(home or {}) | set(away or {})),
        )
    live_odds = odds.get("response") or []
    bets = [b for entry in live_odds for b in entry.get("odds") or []]
    out["live_odds"] = {
        "available": bool(live_odds),
        "markets": len(bets),
        "names": sorted({str(b.get("name")) for b in bets})[:40],
        **live_odds_details(live_odds),
    }
    # Réponses brutes, à télécharger (comparaison avec 1xBet, 12/11/2026) : aucune donnée
    # personnelle, seulement le match et ses cotes.
    out["raw"] = {"asked_at": datetime.now(UTC).isoformat(), "fixtures": body, "odds_live": odds}
    return out


# Champs connus d'une réponse /odds/live ; tout autre champ est montré (un nom de bookmaker
# éventuel, pour savoir d'où viennent les cotes).
_ODDS_ENTRY_KEYS = {"fixture", "league", "teams", "status", "update", "odds"}
_ODDS_BET_KEYS = {"id", "name", "values"}
_ODDS_VALUE_KEYS = {"value", "odd", "handicap", "main", "suspended"}
MAIN_LIVE_MARKETS = ("Fulltime Result", "Match Goals", "Over/Under Line")


def _bookmaker_fields(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}" if path else str(k)
            if "book" in str(k).lower():
                found.append(f"{here} = {v!r}"[:120])
            found += _bookmaker_fields(v, here)
    elif isinstance(node, list):
        for item in node[:200]:
            found += _bookmaker_fields(item, f"{path}[]")
    return found


def live_odds_details(live_odds: list[dict[str, Any]]) -> dict[str, Any]:
    """Valeurs des cotes principales (résultat du match, plus/moins de 2,5 buts), état
    (arrêté, bloqué, suspendu), heure de mise à jour et champs inattendus de /odds/live."""
    if not live_odds:
        return {"main": [], "update": None, "state": None, "unknown_fields": [], "bookmaker": []}
    entry = live_odds[0]
    main = []
    for bet in entry.get("odds") or []:
        if bet.get("name") not in MAIN_LIVE_MARKETS:
            continue
        for v in bet.get("values") or []:
            line = v.get("handicap")
            if bet.get("name") != "Fulltime Result" and str(line) not in ("2.5", "None", ""):
                continue
            main.append(
                {
                    "market": bet.get("name"),
                    "value": v.get("value"),
                    "line": line,
                    "odd": v.get("odd"),
                    "suspended": bool(v.get("suspended")),
                    "main": v.get("main"),
                }
            )
    unknown = sorted(f"réponse.{k}" for k in entry if k not in _ODDS_ENTRY_KEYS)
    for bet in entry.get("odds") or []:
        unknown += [f"marché.{k}" for k in bet if k not in _ODDS_BET_KEYS]
        for v in bet.get("values") or []:
            unknown += [f"cote.{k}" for k in v if k not in _ODDS_VALUE_KEYS]
    fixture_status = (entry.get("fixture") or {}).get("status") or {}
    return {
        "main": main,
        "update": entry.get("update"),
        "state": {
            **{k: entry.get("status", {}).get(k) for k in ("stopped", "blocked", "finished")},
            "elapsed": fixture_status.get("elapsed"),
            "seconds": fixture_status.get("seconds"),
        },
        "unknown_fields": sorted(set(unknown)),
        "bookmaker": _bookmaker_fields(live_odds),
    }
