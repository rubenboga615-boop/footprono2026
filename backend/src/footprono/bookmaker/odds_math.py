"""Cote d'un combiné : une seule règle d'arrondi partout (rapport du 09/11/2026 : le même
coupon affiché 1,84 dans le Coupon intelligent et 1,83 dans la fiche du pari).

Produit des cotes arrondi au millième (cote du pari, base du gain), puis au centième pour
l'affichage ; toujours au plus proche (0,5 vers le haut).
"""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal


def combined_odds(odds: Iterable[Decimal]) -> Decimal:
    """Cote d'un combiné, au millième : 1,20 fois 1,15 fois 1,33 = 1,8354 → 1,835."""
    total = Decimal(1)
    for o in odds:
        total *= o
    return total.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def shown_odds(total: Decimal) -> Decimal:
    """Cote affichée, au centième : 1,835 → 1,84."""
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
