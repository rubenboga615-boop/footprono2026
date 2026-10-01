import pytest
from pydantic import ValidationError

from footprono.core.config import Environment, Settings

from .conftest import make_settings


def test_development_defaults_are_valid() -> None:
    settings = make_settings(environment=Environment.DEVELOPMENT, secret_key=None)
    assert settings.secret_key is None


def test_production_requires_secret_key() -> None:
    with pytest.raises(ValidationError, match="FP_SECRET_KEY"):
        make_settings(environment=Environment.PRODUCTION, secret_key=None)


def test_production_rejects_short_secret_key() -> None:
    with pytest.raises(ValidationError, match="FP_SECRET_KEY"):
        make_settings(environment=Environment.PRODUCTION, secret_key="trop-court")


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="FP_CORS_ORIGINS"):
        make_settings(environment=Environment.PRODUCTION, secret_key="x" * 40, cors_origins=["*"])


def test_production_accepts_valid_configuration() -> None:
    settings = make_settings(
        environment=Environment.PRODUCTION,
        secret_key="x" * 40,
        cors_origins=["https://footprono.example"],
    )
    assert settings.environment is Environment.PRODUCTION


def test_celery_urls_fall_back_to_redis_url() -> None:
    settings = make_settings(redis_url="redis://cache:6379/2")
    assert settings.broker_url == "redis://cache:6379/2"
    assert settings.result_backend == "redis://cache:6379/2"


def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_ENVIRONMENT", "test")
    monkeypatch.setenv("FP_LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.environment is Environment.TEST
    assert settings.log_level == "DEBUG"
