"""Registre des modèles ORM.

Chaque module métier déclare ses tables ; elles sont importées ici pour que
``Base.metadata`` (utilisé par Alembic) les connaisse toutes. Aucune table
métier en phase 0 : elles arrivent avec les phases suivantes (données, comptes…).
"""

from footprono.db.base import Base

__all__ = ["Base"]
