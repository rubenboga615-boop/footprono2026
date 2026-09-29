"""Registre des modèles ORM.

Chaque module métier déclare ses tables ; elles sont importées ici pour que
``Base.metadata`` (utilisé par Alembic) les connaisse toutes.
- ``football.models`` : référentiel, matchs, statistiques, cotes, ingestions (phase 1).
"""

from footprono.db.base import Base
from footprono.football import models as football_models

__all__ = ["Base", "football_models"]
