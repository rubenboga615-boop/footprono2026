"""Formules gratuite et Premium (décision du 30/09/2026).

- Gratuit : matchs, marchés 1X2 / plus-moins de buts / les deux marquent
  (prédictions, offre, paris), bookmaker virtuel, coupons, montante sans
  suggestions, page publique de fiabilité.
- Premium (2 000 F CFA par mois, sans essai automatique) : tous les
  marchés (handicaps, mi-temps, scores exacts, corners, cartons, tirs…),
  suggestions de montante, analyses détaillées.

Le contrôle est fait par le serveur : l'application ne fait qu'afficher.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import status

from footprono.accounts.models import User
from footprono.core.errors import AppError

FREE_MARKETS = frozenset({"1X2", "OU", "BTTS"})
PREMIUM_PRICE = 2000  # F CFA par mois
PREMIUM_DAYS = 30  # durée achetée par paiement
PREMIUM_CURRENCY = "XOF"


class PremiumRequiredError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "premium_required"


def is_premium(user: User | None, now: datetime | None = None) -> bool:
    return user is not None and user.is_premium(now or datetime.now(UTC))


def market_allowed(user: User | None, market: str, now: datetime | None = None) -> bool:
    return market.upper() in FREE_MARKETS or is_premium(user, now)


def require_market(user: User, market: str, now: datetime | None = None) -> None:
    if not market_allowed(user, market, now):
        raise PremiumRequiredError(
            f"le marché {market} est réservé à Premium ; en version gratuite : "
            + ", ".join(sorted(FREE_MARKETS)),
            details={"market": market, "free_markets": sorted(FREE_MARKETS)},
        )


def require_premium(user: User, feature: str, now: datetime | None = None) -> None:
    if not is_premium(user, now):
        raise PremiumRequiredError(f"{feature} : réservé à Premium")


def plan_info(user: User, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    premium = user.is_premium(now)
    return {
        "name": "premium" if premium else "free",
        "premium_until": user.premium_until,
        "days_left": (user.premium_until - now).days if premium and user.premium_until else 0,
        "free_markets": sorted(FREE_MARKETS),
        "premium_price": PREMIUM_PRICE,
        "premium_currency": PREMIUM_CURRENCY,
    }
