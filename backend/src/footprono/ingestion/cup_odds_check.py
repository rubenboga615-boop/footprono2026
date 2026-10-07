"""Vérification avant d'ajouter une coupe : API-Football donne-t-elle des cotes pour ses
prochains matchs, chez nos bookmakers, et sur quels marchés ?

Lecture seule, rien n'est enregistré : quelques requêtes par compétition (prochains
matchs, puis première page de ``/odds``).
"""

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from typing import Any

from footprono.core.config import Settings
from footprono.ingestion import service
from footprono.ingestion.sources import api_football
from footprono.ingestion.sources.api_football_odds import parse_odds_page

# Coupes d'Europe chez API-Football.
CUPS = {2: "Ligue des Champions", 3: "Europa League", 848: "Conférence League"}
# Marchés regardés (noms API-Football) : ceux que le moteur des coupes saurait proposer.
KEY_BETS = ("Match Winner", "Double Chance", "Goals Over/Under", "Both Teams Score")


def cup_season(today: date) -> int:
    """Saison API-Football d'une coupe d'Europe : année de début (juillet → juin)."""
    return today.year if today.month >= 7 else today.year - 1


async def check_cup_odds(
    settings: Settings,
    leagues: list[int],
    season: int,
    log: Callable[[str], None],
) -> dict[str, Any]:
    if settings.api_football_key is None:
        return {"status": "unavailable", "error": "FP_API_FOOTBALL_KEY absente"}
    wanted = {b.lower() for b in settings.odds_bookmakers}
    out: dict[str, Any] = {"status": "ok", "season": season, "leagues": {}}
    async with api_football.ApiFootballClient(
        settings.api_football_key.get_secret_value(),
        budget=40,
        min_remaining=settings.api_football_min_remaining,
        transport=service.api_football_transport,
    ) as client:
        await client.status()
        for league in leagues:
            name = CUPS.get(league, f"compétition {league}")
            fixtures = (await client.get("/fixtures", {"league": league, "next": 10}))["response"]
            upcoming = {int(f["fixture"]["id"]): f for f in fixtures}
            body = await client.get("/odds", {"league": league, "season": season})
            quotes, _, pages = parse_odds_page(body)
            with_odds = {q.fixture_id for q in quotes}
            books: dict[str, set[str]] = defaultdict(set)
            for q in quotes:
                books[q.bookmaker].add(q.bet)
            ours = sorted(b for b in books if b.lower() in wanted)
            summary: dict[str, Any] = {
                "upcoming": len(upcoming),
                "next": [
                    f"{f['fixture']['date'][:10]} {f['teams']['home']['name']} - "
                    f"{f['teams']['away']['name']}"
                    for f in list(upcoming.values())[:3]
                ],
                "fixtures_with_odds_page1": len(with_odds),
                "odds_pages": pages,
                "bookmakers": len(books),
                "our_bookmakers": {b: sorted(set(KEY_BETS) & books[b]) for b in ours},
                "missing_bookmakers": sorted(
                    b
                    for b in settings.odds_bookmakers
                    if b.lower() not in {x.lower() for x in books}
                ),
            }
            out["leagues"][name] = summary
            log(f"{name} (saison {season}) : {len(upcoming)} prochains matchs connus")
            for line in summary["next"]:
                log(f"  {line}")
            if not quotes:
                log("  AUCUNE COTE chez API-Football pour l'instant")
                continue
            log(
                f"  cotes : {len(with_odds)} match(s) sur la 1re page ({pages} page(s)), "
                f"{len(books)} bookmaker(s)"
            )
            for b, bets in summary["our_bookmakers"].items():
                log(f"  {b} : {', '.join(bets) or 'aucun des marchés regardés'}")
            for b in summary["missing_bookmakers"]:
                log(f"  {b} : absent")
        out["requests"] = client.used
    return out
