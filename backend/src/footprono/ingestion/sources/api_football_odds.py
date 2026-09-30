"""Cotes des matchs à venir chez API-Football (``/odds``).

Chaque cote est conservée **telle que publiée** (nom du pari et libellé de la
sélection d'API-Football) ; la traduction vers les marchés du moteur
(``marché|ligne|sélection``) se fait à la lecture par ``map_bet``. Une erreur
de traduction se corrige donc sans perte de données.

Seuls les paris dont la signification est certaine sont traduits.

Handicaps : la ligne est **toujours celle du domicile**, pour les deux (ou
trois) sélections — « Away -0.5 » est le côté extérieur du handicap domicile
moins 0,5. Vérifié le 30/09/2026 sur 2 308 paires de cotes réelles (100 %
cohérentes, contre 12 % pour l'autre lecture ; handicap européen : 287
triplets, 100 % contre 0 %) avec ``handicap_diagnostics``. C'est aussi la
convention des clés du moteur (``AH|ligne domicile|away``).
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


def _signed(value: str, side: str) -> float | None:
    """« Home -0.75 » → -0.75 si ``side`` = « Home »."""
    name, _, line = value.partition(" ")
    if name != side:
        return None
    try:
        return float(line)
    except ValueError:
        return None


def handicap_diagnostics(quotes: list[OddsQuote]) -> dict[str, Any]:
    """Sens des lignes de handicap chez API-Football, établi sur les cotes réelles.

    Pour chaque cote « Home L », on cherche la cote extérieure associée selon
    deux conventions : « Away -L » (chaque équipe avec son propre handicap) ou
    « Away L » (la ligne du domicile répétée). La bonne convention donne une
    marge du bookmaker (somme des inverses des cotes) régulière, entre 1 et
    1,12 ; la mauvaise, des valeurs dispersées. Même principe pour le handicap
    européen (3 issues).
    """
    books: dict[tuple[int, str, str], dict[str, float]] = {}
    for q in quotes:
        if q.bet in ("Asian Handicap", "Handicap Result"):
            books.setdefault((q.fixture_id, q.bookmaker, q.bet), {})[q.value] = float(q.price)
    stats: dict[str, dict[str, list[float]]] = {
        "Asian Handicap": {"own": [], "home_line": []},
        "Handicap Result": {"own": [], "home_line": []},
    }
    for (_fixture, _book, bet), prices in books.items():
        for value, home_price in prices.items():
            line = _signed(value, "Home")
            if line is None:
                continue
            for convention, away_line in (("own", -line + 0.0), ("home_line", line)):
                away = prices.get(f"Away {away_line:+g}") or prices.get(f"Away {away_line:g}")
                if away is None:
                    continue
                total = 1 / home_price + 1 / away
                if bet == "Handicap Result":
                    draw = prices.get(f"Draw {line:+g}") or prices.get(f"Draw {line:g}")
                    if draw is None:
                        continue
                    total += 1 / draw
                stats[bet][convention].append(total)
    out: dict[str, Any] = {}
    for bet, by_convention in stats.items():
        out[bet] = {}
        for convention, totals in by_convention.items():
            if totals:
                ok = sum(1.0 <= t <= 1.12 for t in totals) / len(totals)
                out[bet][convention] = {"pairs": len(totals), "share_plausible": round(ok, 3)}
    return out


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
    if bet in ("Clean Sheet - Home", "Clean Sheet - Away") and value in ("Yes", "No"):
        side = "home" if bet.endswith("Home") else "away"
        return "CLEAN_SHEET", "", side if value == "Yes" else f"{side}_no"
    if bet == "Win To Nil" and value in ("Home", "Away"):
        return "WIN_TO_NIL", "", _SIDES[value]
    if bet == "Results/Both Teams Score":
        result, _, both = value.partition("/")
        if result in _SIDES and both in ("Yes", "No"):
            return "1X2_BTTS", "", f"{_SIDES[result]}/{both.lower()}"
        return None
    if bet == "Result/Total Goals":
        result, _, total = value.partition("/")
        parsed = _over_under(total)
        if result in _SIDES and parsed is not None:
            return "1X2_OU", parsed[0], f"{_SIDES[result]}/{parsed[1]}"
        return None
    if bet == "Total Goals/Both Teams To Score":
        # « o/yes 2.5 » : plus de 2,5 buts et les deux équipes marquent.
        combo, _, line = value.partition(" ")
        total, _, both = combo.partition("/")
        sides = {"o": "over", "u": "under"}
        try:
            line_key = f"{float(line):g}"
        except ValueError:
            return None
        if total in sides and both in ("yes", "no"):
            return "OU_BTTS", line_key, f"{sides[total]}/{both}"
        return None
    if bet in ("Asian Handicap", "Handicap Result"):
        name, _, raw_line = value.partition(" ")
        try:
            hcp = float(raw_line) + 0.0  # « -0 » → 0
        except ValueError:
            return None
        quarter = abs(hcp) <= 3 and (hcp * 4).is_integer()
        if bet == "Asian Handicap" and name in ("Home", "Away") and quarter:
            return "AH", f"{hcp:g}", _SIDES[name]
        if bet == "Handicap Result" and name in _SIDES and hcp in (-3, -2, -1, 1, 2, 3):
            return "EH", f"{hcp:g}", _SIDES[name]
        return None
    if bet == "Winning Margin":
        # « 1 by 2 » : l'équipe 1 (domicile) gagne de 2 buts ; « 2 by 4+ » : extérieur, 4 ou plus.
        # « Draw » et « Score Draw » : sens exact à confirmer, non traduits.
        team, _, rest = value.partition(" by ")
        winner = {"1": "home", "2": "away"}.get(team)
        if winner and rest in ("1", "2", "3", "4+"):
            return "MARGIN", "", f"{winner}+{rest.rstrip('+')}"
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
