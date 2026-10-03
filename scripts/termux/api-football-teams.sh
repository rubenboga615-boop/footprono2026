#!/usr/bin/env bash
# Noms des équipes d'un championnat selon API-Football, saison par saison, et ce
# qu'API-Football couvre pour ce championnat (statistiques, compositions, cotes).
# Sert à relier les équipes entre football-data et API-Football avant d'ajouter
# un championnat. Environ 1 requête par saison et par championnat, plus 1 par
# championnat. La clé API est lue dans backend/.env et n'est jamais affichée.
#
#   bash scripts/termux/api-football-teams.sh            # Portugal (94) et Belgique (144)
#   bash scripts/termux/api-football-teams.sh 88 203     # autres identifiants API-Football
#   FP_AF_FROM=2015 bash scripts/termux/api-football-teams.sh   # depuis 2015 (défaut 2010)
#
# Résultat : ~/storage/downloads/api-football-equipes-<date>.json (à envoyer).
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -d "$HOME/storage/downloads" ] || die "dossier Téléchargements introuvable : lancer d'abord termux-setup-storage"
load_env
"$VENV/bin/python" - "$@" <<'PY'
import json, os, sys, time
from datetime import date
import httpx
from footprono.ingestion.quality import current_season_start

key = os.environ.get("FP_API_FOOTBALL_KEY")
if not key:
    sys.exit("FP_API_FOOTBALL_KEY absente de backend/.env")
leagues = [int(a) for a in sys.argv[1:]] or [94, 144]
first = int(os.environ.get("FP_AF_FROM", "2010"))
client = httpx.Client(base_url="https://v3.football.api-sports.io", timeout=30,
                      headers={"x-apisports-key": key})
remaining = "?"


def get(path: str, **params: object) -> dict:
    global remaining
    r = client.get(path, params=params)
    remaining = r.headers.get("x-ratelimit-requests-remaining", remaining)
    time.sleep(0.3)
    body = r.json()
    if body.get("errors"):
        print(f"  {path} {params} : erreurs {body['errors']}")
    return body


out = {"date": f"{date.today():%Y-%m-%d}", "leagues": {}}
for league in leagues:
    info = get("/leagues", id=league).get("response") or []
    if not info:
        print(f"Championnat {league} inconnu d'API-Football")
        continue
    name = f"{info[0]['country']['name']} · {info[0]['league']['name']}"
    seasons = {s["year"]: s for s in info[0]["seasons"]}
    print(f"\n== {league} · {name}")
    entry = {"name": name, "seasons": {}}
    for year in range(first, current_season_start() + 1):
        s = seasons.get(year)
        if s is None:
            print(f"  {year} : saison absente d'API-Football")
            continue
        cov = s.get("coverage") or {}
        fx = cov.get("fixtures") or {}
        teams = [
            {"id": t["team"]["id"], "name": t["team"]["name"]}
            for t in get("/teams", league=league, season=year).get("response") or []
        ]
        entry["seasons"][year] = {
            "teams": sorted(teams, key=lambda t: t["name"]),
            "coverage": {
                "statistiques": fx.get("statistics_fixtures"),
                "compositions": fx.get("lineups"),
                "evenements": fx.get("events"),
                "cotes": cov.get("odds"),
                "blessures": cov.get("injuries"),
            },
        }
        flags = " · ".join(f"{k} {'oui' if v else 'non'}" for k, v in entry["seasons"][year]["coverage"].items())
        print(f"  {year} : {len(teams)} équipes · {flags}")
    out["leagues"][league] = entry

path = os.path.expanduser(f"~/storage/downloads/api-football-equipes-{date.today():%Y%m%d}.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"\nFichier prêt : {path}")
print(f"Requêtes API-Football restantes aujourd'hui : {remaining}")
PY
