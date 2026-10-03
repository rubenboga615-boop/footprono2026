#!/usr/bin/env bash
# Test direct des cotes d'API-Football, hors de l'application (1 requête).
# Affiche, pour les prochains matchs d'un championnat, la date de mise à jour
# annoncée par API-Football et la cote 1xBet du résultat du match.
# La clé API est lue dans backend/.env et n'est jamais affichée.
#   bash scripts/termux/check-odds.sh            # Ligue 1
#   bash scripts/termux/check-odds.sh 39         # Premier League (140 Liga, 135 Serie A, 78 Bundesliga)
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

load_env
LEAGUE="${1:-61}"
"$VENV/bin/python" - "$LEAGUE" <<'PY'
import os, sys
from datetime import datetime, timezone
import httpx
from footprono.ingestion.quality import current_season_start

key = os.environ.get("FP_API_FOOTBALL_KEY")
if not key:
    sys.exit("FP_API_FOOTBALL_KEY absente de backend/.env")
league, season = sys.argv[1], current_season_start()
r = httpx.get(
    "https://v3.football.api-sports.io/odds",
    params={"league": league, "season": season, "bookmaker": 11},  # 11 = 1xBet
    headers={"x-apisports-key": key},
    timeout=30,
)
body = r.json()
now = datetime.now(timezone.utc)
print(f"Requête : /odds?league={league}&season={season}&bookmaker=11 (1xBet)")
print(f"Réponse HTTP {r.status_code}, erreurs : {body.get('errors') or 'aucune'}, "
      f"matchs : {body.get('results')}, pages : {body.get('paging')}")
print(f"Requêtes restantes aujourd'hui : {r.headers.get('x-ratelimit-requests-remaining', '?')}")
print()
for item in body.get("response", [])[:10]:
    fixture = item["fixture"]
    updated = item.get("update") or "?"
    age = ""
    try:
        delta = now - datetime.fromisoformat(updated)
        age = f" (il y a {delta.days} j {delta.seconds // 3600} h)"
    except ValueError:
        pass
    prices = ""
    for book in item.get("bookmakers", []):
        for bet in book.get("bets", []):
            if bet.get("name") == "Match Winner":
                prices = " / ".join(f"{v['value']} {v['odd']}" for v in bet["values"])
    print(f"match {fixture['id']} le {fixture.get('date', '?')[:16]}")
    print(f"   mise à jour API-Football : {updated}{age}")
    print(f"   1xBet 1-N-2 : {prices or 'absent'}")
if not body.get("response"):
    print("Aucune cote renvoyée pour ce championnat et cette saison.")
PY
