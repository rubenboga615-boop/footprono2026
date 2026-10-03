"""Moteur de prédiction.

Indépendant de FastAPI et de Celery : utilisable seul pour l'entraînement, le
backtest et la production, avec le même code (principe n° 2).

- ``history`` : chargement de l'historique en tableaux numpy ;
- ``goals`` : modèle des buts (Dixon-Coles pondéré dans le temps, xG optionnels) ;
- ``scores`` : distribution jointe mi-temps / fin de match ;
- ``markets`` : tous les marchés dérivés de cette distribution ;
- ``context`` / ``correction`` : contexte du match et couche de correction ;
- ``counts`` : corners, cartons et tirs ;
- ``backtest`` : évaluation stricte dans le temps.
"""

# Version enregistrée avec chaque prédiction. À changer à chaque modification
# du moteur qui change les probabilités (réglages, modèles, correction).
ENGINE_VERSION = "2.3"  # 2.3 : niveaux de données (Portugal, Belgique, engine/tiers.py)
# 2.2 : passes dangereuses dans le signal d'occasions, arbitres regroupés
# 2.1 : écart de buts 1/2/3/4+, clean sheet non, plus/moins + BTTS
