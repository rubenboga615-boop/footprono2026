"""Marchés retenus pour les choix automatiques (Coupon intelligent, montante).

Décidé sur les audits hors échantillon (docs/MARCHES.md, docs/MOTEUR.md) :

- retirés de l'application : le moteur n'y fait pas mieux que la fréquence
  du championnat (mi-temps « les deux marquent », mi-temps la plus
  prolifique, pair / impair) ;
- cartons et points de cartons : surestimés au-dessus de 50 %, aucune
  correction prouvée ;
- combinés dans un même match, score exact, mi-temps / fin de match, écart de
  buts : choisis comme « meilleur angle », ils sont surestimés (malédiction
  du gagnant) ou trop improbables pour un coupon.

L'utilisateur peut toujours les jouer lui-même ; ils ne sont simplement
jamais proposés automatiquement.
"""

from footprono.engine.markets import WITHDRAWN_MARKETS

NOT_AUTOMATIC = frozenset(
    {"CS", "HTFT", "1X2_OU", "1X2_BTTS", "OU_BTTS", "MARGIN", "BOOKING_POINTS_OU"}
)
NOT_AUTOMATIC_PREFIXES = ("CARDS_",)


def automatic(market: str) -> bool:
    """Le marché peut-il être choisi automatiquement ?"""
    return (
        market not in WITHDRAWN_MARKETS
        and market not in NOT_AUTOMATIC
        and not market.startswith(NOT_AUTOMATIC_PREFIXES)
    )
