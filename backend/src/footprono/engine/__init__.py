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
ENGINE_VERSION = "2.0"
