"""Niveaux de données : le moteur s'adapte à ce que chaque championnat fournit.

- **Niveau 1** (5 grands championnats) : xG Understat et passes dangereuses ;
  réglages ``GoalsConfig()`` d'origine, couche de correction, corners et cartons.
- **Niveau 2** (tirs, sans xG) : xG « maison » tirés des tirs, mémoire d'un an,
  profil de buts modéré, écart favori / outsider recalé sur les saisons passées
  du niveau 2 ; ni correction « sans enjeu » (sans effet sur ces championnats), ni
  corners/cartons/tirs (non mesurés), ni « les deux marquent » (pas mieux que
  la fréquence du championnat sur 2022-26).

Tout est mesuré dans docs/MOTEUR.md (« Championnats sans xG », « Étude Portugal
et Belgique », « Championnats candidats ») : réglages choisis sur 2019-22 (Portugal,
Belgique), vérifiés sur 2022-26 et appliqués tels quels aux Pays-Bas, à la Grèce et
à la Turquie.
"""

from dataclasses import dataclass, field, replace

import numpy as np

from footprono.engine.goals import GoalsConfig
from footprono.engine.history import History

# xG « maison » : relation apprise sur les 5 grands championnats, saisons ≤ 2021-22
# (jamais sur les championnats de niveau 2) :
# xG = 0,018 + 0,218 x tir cadré + 0,060 x tir non cadré - 0,016 x corner.
SHOT_XG = (0.018, 0.218, 0.060, -0.016)
# Les tirs resserrent l'écart entre équipes (l'équipe menée tire plus) : chaque valeur
# est écartée de la moyenne du championnat (domicile et extérieur à part) de ce facteur.
SHOT_XG_STRETCH = 1.5

# Marchés retirés au niveau 2 : « les deux marquent » et ses combinaisons.
NO_BTTS = frozenset({"BTTS", "1X2_BTTS", "OU_BTTS", "HT_BTTS"})


@dataclass(frozen=True)
class Tier:
    level: int
    goals: GoalsConfig = field(default_factory=GoalsConfig)
    correction: bool = True
    # Écart favori / outsider recalé sur les saisons passées du même niveau
    # (fit_level_stretch) : au niveau 2, le modèle des buts sous-estime les favoris.
    level_stretch: bool = False
    counts: bool = True
    withdrawn: frozenset[str] = frozenset()


TIER_1 = Tier(level=1)
TIER_2 = Tier(
    level=2,
    goals=GoalsConfig(xg_weight=0.5, deep_weight=0.0, half_life_days=365.0, profile_shrink=0.5),
    correction=False,
    level_stretch=True,
    counts=False,
    withdrawn=NO_BTTS,
)

# Pologne, Tchéquie, Croatie, Roumanie : « clean sheet » mal calibré à l'audit 2022-25
# (annoncé 44,6 %, observé 39,6 % sur 1 370 cas) : retiré pour eux seulement.
TIER_2_NO_CLEAN_SHEET = replace(TIER_2, withdrawn=NO_BTTS | {"CLEAN_SHEET"})

# Niveau 2 : tirs sans xG (football-data, ou API-Football depuis la Suisse).
_TIER_2_CODES = "POR BEL NED GRE TUR SCO SUI NOR SWE DEN AUT"
TIERS: dict[str, Tier] = {
    **{code: TIER_2 for code in _TIER_2_CODES.split()},
    **{code: TIER_2_NO_CLEAN_SHEET for code in ("POL", "CZE", "CRO", "ROU")},
}


def tier(competition: str) -> Tier:
    return TIERS.get(competition, TIER_1)


def goals_config(competition: str, base: GoalsConfig | None = None) -> GoalsConfig:
    """Réglages du modèle des buts : ``base`` (défaut d'origine) au niveau 1."""
    t = tier(competition)
    return t.goals if t.level > 1 else (base or GoalsConfig())


def market_allowed(competition: str, key: str) -> bool:
    return key.split("|", 1)[0] not in tier(competition).withdrawn


def apply_shot_xg(hist: History) -> None:
    """Remplit les xG des championnats de niveau 2 à partir des tirs (sur place).

    Un match sans tirs (saisons anciennes) garde des xG absents : le modèle des
    buts utilise alors les vrais buts, comme pour tout match sans xG. Moyennes de
    l'étirement : tout l'historique du championnat ; le niveau absolu ne compte pas
    (le modèle remet les xG au niveau des vrais buts sur sa fenêtre).
    """
    if "shots" not in hist.stats or "shots_on_target" not in hist.stats:
        return
    b0, b_on, b_off, b_corner = SHOT_XG
    sh, sa = hist.stats["shots"]
    th, ta = hist.stats["shots_on_target"]
    ch, ca = hist.stats.get("corners", (np.zeros_like(sh), np.zeros_like(sa)))
    xh = np.clip(b0 + b_on * th + b_off * (sh - th) + b_corner * ch, 0.05, None)
    xa = np.clip(b0 + b_on * ta + b_off * (sa - ta) + b_corner * ca, 0.05, None)
    for comp, t in TIERS.items():
        if t.level != 2:
            continue
        m = hist.competition == comp
        if not m.any() or np.isnan(xh[m]).all():
            continue
        mh, ma = np.nanmean(xh[m]), np.nanmean(xa[m])
        hist.hxg[m] = np.clip(mh + SHOT_XG_STRETCH * (xh[m] - mh), 0.05, None)
        hist.axg[m] = np.clip(ma + SHOT_XG_STRETCH * (xa[m] - ma), 0.05, None)
