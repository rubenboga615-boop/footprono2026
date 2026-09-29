"""Base déclarative SQLAlchemy commune à tous les modèles."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Conventions de nommage explicites : les migrations Alembic restent
# déterministes (mêmes noms de contraintes sur toutes les machines).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
