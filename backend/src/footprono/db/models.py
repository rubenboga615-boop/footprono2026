"""Registre des modèles ORM.

Chaque module métier déclare ses tables ; elles sont importées ici pour que
``Base.metadata`` (utilisé par Alembic) les connaisse toutes.
- ``football.models`` : référentiel, matchs, statistiques, cotes, ingestions (phase 1).
- ``predictions.models`` : exécutions du moteur et prédictions par match (phase 2).
- ``accounts.models`` : comptes et portefeuille fictif (phase 4).
- ``bookmaker.models`` / ``bookmaker.montante_models`` : paris, montantes (phase 4).
"""

from footprono.accounts import models as account_models
from footprono.bookmaker import models as bookmaker_models
from footprono.bookmaker import montante_models
from footprono.db.base import Base
from footprono.football import models as football_models
from footprono.notifications import models as notification_models
from footprono.payments import models as payment_models
from footprono.predictions import models as prediction_models

__all__ = [
    "Base",
    "account_models",
    "bookmaker_models",
    "football_models",
    "montante_models",
    "notification_models",
    "payment_models",
    "prediction_models",
]
