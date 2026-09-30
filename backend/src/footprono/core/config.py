"""Configuration de l'application.

Toute la configuration vient des variables d'environnement (préfixe ``FP_``),
éventuellement chargées depuis un fichier ``.env``. En production, les secrets
sont obligatoires : l'application refuse de démarrer plutôt que de tourner avec
une valeur par défaut prévisible.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_SECRET_LENGTH = 32


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    app_name: str = "FootProno"
    api_prefix: str = "/api/v1"

    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://footprono:footprono@localhost:5432/footprono"),
    )
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)

    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))
    celery_broker_url: RedisDsn | None = None
    celery_result_backend: RedisDsn | None = None

    secret_key: SecretStr | None = None
    api_football_key: SecretStr | None = None
    # Requêtes API-Football au plus par fichier (une ligue, une saison) téléchargé.
    api_football_budget: int = Field(default=1500, ge=1)
    # Requêtes quotidiennes laissées à d'autres usages (archivage des cotes en
    # direct : une cote non capturée est perdue, une statistique se redemande).
    api_football_min_remaining: int = Field(default=200, ge=0)
    cors_origins: list[str] = Field(default_factory=list)

    # Fichiers bruts archivés (football-data, Understat…), nommés par empreinte.
    raw_data_dir: Path = Path("data/raw")

    log_level: str = "INFO"
    log_json: bool = True

    # Délai maximal d'une vérification de dépendance (base, Redis) dans /ready.
    readiness_timeout_seconds: float = Field(default=2.0, gt=0)

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.environment is Environment.PRODUCTION:
            secret = self.secret_key.get_secret_value() if self.secret_key else ""
            if len(secret) < _MIN_SECRET_LENGTH:
                raise ValueError(
                    f"FP_SECRET_KEY est obligatoire en production "
                    f"({_MIN_SECRET_LENGTH} caractères minimum)"
                )
            if "*" in self.cors_origins:
                raise ValueError("FP_CORS_ORIGINS ne peut pas contenir '*' en production")
        return self

    @property
    def broker_url(self) -> str:
        return str(self.celery_broker_url or self.redis_url)

    @property
    def result_backend(self) -> str:
        return str(self.celery_result_backend or self.redis_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
