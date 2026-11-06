"""Réglages du serveur : chaque réglage du modèle deploy/.env.example est transmis au
serveur par deploy/docker-compose.yml (sinon, écrit dans .env, il serait ignoré sans
message : FP_CUPS_PREDICTIONS et FP_PRIVACY_PAYMENT_PROVIDER l'étaient)."""

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def test_every_example_setting_reaches_the_server() -> None:
    example = (DEPLOY / ".env.example").read_text(encoding="utf-8")
    compose = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    names = set(re.findall(r"^(FP_[A-Z0-9_]+)=", example, flags=re.MULTILINE))
    assert "FP_CUPS_PREDICTIONS" in names
    missing = sorted(n for n in names if "${" + n not in compose)
    assert missing == []
