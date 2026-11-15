"""Prix d'une sélection : probabilité calée sur la référence fois cote proposée.

1,00 = la cote proposée est exactement la cote juste selon la référence ; 0,95 = le joueur
paie 5 % de marge. Mesuré sur les matchs réels du 30/09 au 14/11/2026 (14 260 sélections
de buts réglées, cotes jouables de l'application, docs/ETUDE_MOTEUR_V3_2026-11-15.md) :

    prix < 0,90      réussite 18,5 %   rendement -24,5 % ± 5,7
    0,90 à 0,94      52,6 %            -9,9 % ± 3,8
    0,94 à 0,97      67,2 %            -5,1 % ± 3,1
    0,97 à 1,00      72,6 %            -3,6 % ± 3,7

Le même calcul avec la probabilité du moteur seul ne classe rien (rendement de -3 % à -7 %
dans toutes les tranches) : le prix n'a de sens que pour un match calé sur la référence, et
pour un marché de buts (corners et tirs gardent la probabilité du moteur).

Au-dessus de 1,03 la cote proposée dépasse nettement la cote juste : presque toujours une
cote qui n'a pas suivi le marché (112 sélections, résultats erratiques). Elle n'est jamais
préférée.
"""

from decimal import Decimal

GOOD_FROM = 0.97  # « bien payé »
FAIR_FROM = 0.94
SUSPECT_ABOVE = 1.03

# Tranches, de la meilleure à la moins bonne (ordre de préférence des choix automatiques).
GOOD, NEUTRAL, EXPENSIVE, SUSPECT = 0, 1, 2, 3


def price(probability: float, odds: Decimal | float) -> float:
    return probability * float(odds)


def tier(probability: float, odds: Decimal | float, priced: bool) -> int:
    """Tranche de prix ; ``priced`` faux (match non calé, corners, tirs) : neutre."""
    if not priced:
        return NEUTRAL
    value = price(probability, odds)
    if value > SUSPECT_ABOVE:
        return SUSPECT
    if value >= GOOD_FROM:
        return GOOD
    if value >= FAIR_FROM:
        return NEUTRAL
    return EXPENSIVE


LABELS = {GOOD: "good", NEUTRAL: "neutral", EXPENSIVE: "expensive", SUSPECT: "suspect"}


def describe(probability: float | None, odds: Decimal | float, priced: bool) -> dict[str, object]:
    """Prix et tranche pour l'affichage ; rien si le prix n'a pas de sens pour ce match."""
    if probability is None or not priced:
        return {"price": None, "price_tier": None}
    return {
        "price": round(price(probability, odds), 3),
        "price_tier": LABELS[tier(probability, odds, True)],
    }
