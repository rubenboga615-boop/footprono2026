"""Fixtures de test.

Les tests d'intégration tournent contre un vrai PostgreSQL et un vrai Redis
(jamais de simulation de la base) :

    FP_TEST_DATABASE_URL=postgresql+asyncpg://footprono:footprono@localhost:5432/footprono_test
    FP_TEST_REDIS_URL=redis://localhost:6379/15
"""

import os
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from footprono.core.config import Environment, Settings
from footprono.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "FP_TEST_DATABASE_URL",
    "postgresql+asyncpg://footprono:footprono@localhost:5432/footprono_test",
)
TEST_REDIS_URL = os.environ.get("FP_TEST_REDIS_URL", "redis://localhost:6379/15")


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "database_url": TEST_DATABASE_URL,
        "redis_url": TEST_REDIS_URL,
        "log_json": True,
        "readiness_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
