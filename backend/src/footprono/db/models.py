"""Registre des modèles ORM.

Chaque module métier déclare ses tables ; elles sont importées ici pour que
``Base.metadata`` (utilisé par Alembic) les connaisse toutes.
- ``football.models`` : référentiel, matchs, statistiques, cotes, ingestions (phase 1).
- ``predictions.models`` : exécutions du moteur et prédictions par match (phase 2).
- ``accounts.models`` : comptes et portefeuille fictif (phase 4).
"""

from footprono.accounts import models as account_models
from footprono.db.base import Base
from footprono.football import models as football_models
from footprono.predictions import models as prediction_models

__all__ = ["Base", "account_models", "football_models", "prediction_models"]
