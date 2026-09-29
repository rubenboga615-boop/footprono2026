"""Le worker Celery consomme réellement des tâches via Redis."""

import pytest
from celery import Celery
from celery.contrib.testing.worker import start_worker

from footprono import __version__
from footprono.worker.celery_app import create_celery

from .conftest import make_settings


@pytest.fixture(scope="module")
def celery_test_app() -> Celery:
    app = create_celery(make_settings())
    app.loader.import_default_modules()
    import footprono.worker.tasks  # noqa: F401  (enregistre les tâches)

    return app


def test_ping_task_is_registered(celery_test_app: Celery) -> None:
    assert "footprono.ping" in celery_test_app.tasks


def test_ping_runs_through_real_broker(celery_test_app: Celery) -> None:
    with start_worker(celery_test_app, perform_ping_check=False, pool="solo"):
        result = celery_test_app.send_task("footprono.ping")
        assert result.get(timeout=10) == {"status": "ok", "version": __version__}


def test_current_season_ingestion_is_scheduled(celery_test_app: Celery) -> None:
    assert "footprono.ingest_current_season" in celery_test_app.tasks
    schedule = celery_test_app.conf.beat_schedule["ingest-current-season"]
    assert schedule["task"] == "footprono.ingest_current_season"
