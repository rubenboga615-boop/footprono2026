"""Cotes des matchs à venir chez API-Football (``/odds``).

Chaque cote est conservée **telle que publiée** (nom du pari et libellé de la
sélection d'API-Football) ; la traduction vers les marchés du moteur
(``marché|ligne|sélection``) se fait à la lecture par ``map_bet``. Une erreur
de traduction se corrige donc sans perte de données.

Seuls les paris dont la signification est certaine sont traduits. Le
handicap asiatique ne l'est pas encore : le sens de sa ligne dans les libellés
d'API-Football reste à vérifier sur des cotes réelles.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Bookmakers de référence interne : collectés pour mesurer le moteur, jamais affichés.
REFERENCE_ONLY = frozenset({"Pinnacle"})


@dataclass(frozen=True)
class OddsQuote:
    fixture_id: int
    bookmaker: str
    bet: str
    value: str
    price: Decimal
    updated_at: datetime | None


def _updated(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC)


def parse_odds_page(body: dict[str, Any]) -> tuple[list[OddsQuote], int, int]:
    """Une page de ``/odds`` → cotes, page courante, nombre de pages."""
    quotes = []
    for item in body.get("response", []):
        fixture_id = int(item["fixture"]["id"])
        updated = _updated(item.get("update"))
        for book in item.get("bookmakers", []):
            for bet in book.get("bets", []):
                for v in bet.get("values", []):
                    try:
                        price = Decimal(str(v["odd"]))
                    except (InvalidOperation, KeyError):
                        continue
                    if price <= 1:
                        continue
                    quotes.append(
                        OddsQuote(
                            fixture_id=fixture_id,
                            bookmaker=str(book["name"]),
                            bet=str(bet["name"]),
                            value=str(v["value"]),
                            price=price,
                            updated_at=updated,
                        )
                    )
    paging = body.get("paging") or {}
    return quotes, int(paging.get("current", 1)), int(paging.get("total", 1))


_SIDES = {"Home": "home", "Draw": "draw", "Away": "away"}
_DOUBLE = {"Home/Draw": "1X", "Draw/Away": "X2", "Home/Away": "12"}
_HALF = {"1st Half": "first", "2nd Half": "second", "Draw": "equal"}


def _over_under(value: str) -> tuple[str, str] | None:
    """« Over 2.5 » → (« 2.5 », « over »)."""
    side, _, line = value.partition(" ")
    if side not in ("Over", "Under"):
        return None
    try:
        return f"{float(line):g}", side.lower()
    except ValueError:
        return None


def map_bet(bet: str, value: str) -> tuple[str, str, str] | None:
    """Pari API-Football → (marché, ligne, sélection) du moteur ; None si non traduit."""
    if bet == "Match Winner" and value in _SIDES:
        return "1X2", "", _SIDES[value]
    if bet == "First Half Winner" and value in _SIDES:
        return "HT_1X2", "", _SIDES[value]
    if bet == "Double Chance" and value in _DOUBLE:
        return "DC", "", _DOUBLE[value]
    if bet == "Home/Away" and value in ("Home", "Away"):
        return "DNB", "", _SIDES[value]
    if bet == "Both Teams Score" and value in ("Yes", "No"):
        return "BTTS", "", value.lower()
    if bet == "Both Teams Score - First Half" and value in ("Yes", "No"):
        return "HT_BTTS", "", value.lower()
    if bet == "Odd/Even" and value in ("Odd", "Even"):
        return "ODD_EVEN", "", value.lower()
    if bet == "Highest Scoring Half" and value in _HALF:
        return "HIGHEST_HALF", "", _HALF[value]
    if bet == "HT/FT Double":
        first, _, second = value.partition("/")
        if first in _SIDES and second in _SIDES:
            return "HTFT", "", f"{_SIDES[first]}/{_SIDES[second]}"
        return None
    if bet == "Exact Score":
        home, _, away = value.partition(":")
        if home.isdigit() and away.isdigit() and int(home) <= 5 and int(away) <= 5:
            return "CS", "", f"{int(home)}-{int(away)}"
        return None
    over_under_markets = {
        "Goals Over/Under": "OU",
        "Goals Over/Under First Half": "HT_OU",
        "Total - Home": "TEAM_OU_HOME",
        "Total - Away": "TEAM_OU_AWAY",
        "Corners Over Under": "CORNERS_OU",
        "Cards Over/Under": "CARDS_OU",
    }
    if bet in over_under_markets:
        parsed = _over_under(value)
        if parsed is not None:
            return over_under_markets[bet], parsed[0], parsed[1]
    return None
