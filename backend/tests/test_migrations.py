"""Les migrations s'appliquent et se défont proprement sur un vrai PostgreSQL."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from .conftest import TEST_DATABASE_URL

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    return config


def test_single_migration_head() -> None:
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert len(heads) == 1


def test_upgrade_and_downgrade_roundtrip() -> None:
    config = _config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_models_match_migrations() -> None:
    config = _config()
    command.upgrade(config, "head")
    command.check(config)  # échoue si un modèle diverge du schéma migré
