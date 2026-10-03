#!/usr/bin/env bash
# Historique d'API-Football (matchs, journées, statistiques de match : tirs, corners…)
# pour étudier de nouveaux championnats AVANT de les ajouter à l'application.
# Rien n'est chargé dans la base : les fichiers sont rangés puis réunis dans une
# archive à envoyer pour l'étude. Aucune donnée personnelle ; la clé API est lue dans
# backend/.env et n'est jamais écrite ni affichée.
#
#   bash scripts/termux/api-football-history.sh               # tous les championnats ci-dessous
#   bash scripts/termux/api-football-history.sh NOR SWE AUS   # championnats au choix
#   FP_AF_FROM=2016 bash scripts/termux/api-football-history.sh   # depuis 2016 (défaut 2018)
#   FP_AF_RESERVE=3000 bash scripts/termux/api-football-history.sh  # requêtes laissées au serveur
#
# Coût : 1 requête par saison pour la liste des matchs, puis 1 par match terminé pour
# ses statistiques (environ 250 par saison). Le script s'arrête de lui-même quand il ne
# reste plus que FP_AF_RESERVE requêtes du jour (défaut 1500, pour le serveur) : le
# relancer le lendemain reprend où il s'était arrêté (rien n'est redemandé).
# Résultat : ~/storage/downloads/api-football-historique-<date>.tar.gz (à envoyer).
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -d "$HOME/storage/downloads" ] || die "dossier Téléchargements introuvable : lancer d'abord termux-setup-storage"
load_env
"$VENV/bin/python" - "$@" <<'PY'
import json, os, sys, tarfile, time
from collections import Counter
from datetime import date
import httpx
from footprono.ingestion.quality import current_season_start

# Premières divisions des pays habitués aux coupes d'Europe (et l'Australie).
# code : (identifiant API-Football, pays chez API-Football, nom affiché)
LEAGUES = {
    "SWZ": (207, "Switzerland", "Suisse · Super League"),
    "NOR": (103, "Norway", "Norvège · Eliteserien"),
    "SWE": (113, "Sweden", "Suède · Allsvenskan"),
    "DNK": (119, "Denmark", "Danemark · Superliga"),
    "AUT": (218, "Austria", "Autriche · Bundesliga"),
    "POL": (106, "Poland", "Pologne · Ekstraklasa"),
    "ROU": (283, "Romania", "Roumanie · Liga I"),
    "AUS": (188, "Australia", "Australie · A-League"),
    "CZE": (345, "Czech-Republic", "Tchéquie · 1re division"),
    "CRO": (210, "Croatia", "Croatie · HNL"),
    "SRB": (286, "Serbia", "Serbie · Super Liga"),
    "ISR": (383, "Israel", "Israël · Ligat ha'Al"),
    "CYP": (318, "Cyprus", "Chypre · 1re division"),
}
FINISHED = {"FT", "AET", "PEN"}

key = os.environ.get("FP_API_FOOTBALL_KEY")
if not key:
    sys.exit("FP_API_FOOTBALL_KEY absente de backend/.env")
args = [a.upper() for a in sys.argv[1:]] or list(LEAGUES)
unknown = [a for a in args if a not in LEAGUES]
if unknown:
    sys.exit(f"Inconnu : {', '.join(unknown)}. Choix possibles : {', '.join(LEAGUES)}")
first = int(os.environ.get("FP_AF_FROM", "2018"))
reserve = int(os.environ.get("FP_AF_RESERVE", "1500"))
current = current_season_start()
out = os.path.expanduser("~/storage/downloads/api-football-historique")
client = httpx.Client(
    base_url=os.environ.get("FP_AF_BASE_URL", "https://v3.football.api-sports.io"),
    timeout=30, headers={"x-apisports-key": key},
)
remaining: int | None = None
used = 0


class QuotaReached(Exception):
    pass


def get(path: str, **params: object) -> list:
    """Une requête ; respecte la limite par minute et la réserve du jour."""
    global remaining, used
    if remaining is not None and remaining <= reserve:
        raise QuotaReached
    for attempt in range(4):
        try:
            r = client.get(path, params=params)
        except httpx.HTTPError as e:
            if attempt == 3:
                raise
            print(f"  réseau ({type(e).__name__}), nouvel essai dans 10 s", flush=True)
            time.sleep(10)
            continue
        used += 1
        if "x-ratelimit-requests-remaining" in r.headers:
            remaining = int(r.headers["x-ratelimit-requests-remaining"])
        time.sleep(0.25)
        body = r.json()
        errors = body.get("errors") or {}
        if errors:
            text = json.dumps(errors, ensure_ascii=False)
            if "requests" in errors:  # quota du jour épuisé
                raise QuotaReached
            if "rateLimit" in errors and attempt < 3:  # limite par minute
                print("  limite par minute atteinte, pause d'une minute", flush=True)
                time.sleep(60)
                continue
            print(f"  {path} {params} : erreur {text}", flush=True)
            return []
        return body.get("response") or []
    return []


def load_json(path: str) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def done_ids(path: str) -> set[int]:
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {json.loads(line)["fixture"] for line in f if line.strip()}


plan: list[tuple[str, int, bool]] = []  # (code, saison, statistiques couvertes)
stopped = False
try:
    # 1. Liste des matchs de chaque saison (peu de requêtes) : tout le tableau d'abord.
    for code in args:
        league_id, country, label = LEAGUES[code]
        info_path = os.path.join(out, code, "league.json")
        if os.path.exists(info_path) and date.fromtimestamp(os.path.getmtime(info_path)) == date.today():
            info = load_json(info_path)
        else:
            info = get("/leagues", id=league_id)
            save_json(info_path, info)
        if not info:
            print(f"\n== {code} · {label} : championnat {league_id} inconnu d'API-Football, ignoré")
            continue
        got = info[0]["country"]["name"]
        if got.replace("-", " ").lower() != country.replace("-", " ").lower():
            print(f"\n== {code} : l'identifiant {league_id} est « {got} · {info[0]['league']['name']} », "
                  f"pas {country} : ignoré (à signaler)")
            continue
        print(f"\n== {code} · {got} · {info[0]['league']['name']}", flush=True)
        seasons = {s["year"]: s for s in info[0]["seasons"]}
        for year in range(first, current + 1):
            s = seasons.get(year)
            if s is None:
                print(f"  {year} : saison absente d'API-Football")
                continue
            stats_ok = bool(((s.get("coverage") or {}).get("fixtures") or {}).get("statistics_fixtures"))
            path = os.path.join(out, code, str(year), "fixtures.json")
            if not os.path.exists(path) or year >= current - 1:
                save_json(path, get("/fixtures", league=league_id, season=year))
            fixtures = load_json(path)
            finished = sum(1 for f in fixtures if f["fixture"]["status"]["short"] in FINISHED)
            print(f"  {year} : {len(fixtures)} matchs, {finished} terminés · "
                  f"statistiques {'oui' if stats_ok else 'non'}", flush=True)
            plan.append((code, year, stats_ok))

    # 2. Statistiques de chaque match terminé (1 requête par match).
    todo = 0
    for code, year, stats_ok in plan:
        if stats_ok:
            fixtures = load_json(os.path.join(out, code, str(year), "fixtures.json"))
            done = done_ids(os.path.join(out, code, str(year), "statistics.jsonl"))
            todo += sum(1 for f in fixtures if f["fixture"]["status"]["short"] in FINISHED
                        and f["fixture"]["id"] not in done)
    left_today = "?" if remaining is None else max(0, remaining - reserve)
    print(f"\nStatistiques à demander : {todo} matchs (possibles aujourd'hui : {left_today})", flush=True)
    for code, year, stats_ok in plan:
        if not stats_ok:
            continue
        folder = os.path.join(out, code, str(year))
        fixtures = load_json(os.path.join(folder, "fixtures.json"))
        stats_path = os.path.join(folder, "statistics.jsonl")
        done = done_ids(stats_path)
        pending = [f["fixture"]["id"] for f in fixtures
                   if f["fixture"]["status"]["short"] in FINISHED and f["fixture"]["id"] not in done]
        if not pending:
            continue
        print(f"  {code} {year} : {len(pending)} matchs", flush=True)
        with open(stats_path, "a", encoding="utf-8") as f:
            for n, fixture_id in enumerate(pending, start=1):
                response = get("/fixtures/statistics", fixture=fixture_id)
                f.write(json.dumps({"fixture": fixture_id, "response": response}, ensure_ascii=False) + "\n")
                f.flush()
                if n % 50 == 0:
                    print(f"    {n}/{len(pending)} — requêtes restantes aujourd'hui {remaining}", flush=True)
except QuotaReached:
    stopped = True
    print(f"\nRéserve du jour atteinte ({reserve} requêtes laissées au serveur) : arrêt propre.")
except KeyboardInterrupt:
    stopped = True
    print("\nInterrompu : ce qui est téléchargé est gardé.")

# 3. Résumé et archive (même partielle : utile pour commencer l'étude).
lines = [f"API-Football, téléchargé le {date.today():%d/%m/%Y}, saisons {first}-{current}",
         "Par saison : matchs, terminés, avec statistiques (vides), journées.", ""]
missing = 0
for code in args:
    folder = os.path.join(out, code)
    if not os.path.isdir(folder):
        continue
    years = sorted(int(y) for y in os.listdir(folder) if y.isdigit())
    if not years:
        continue
    covered = {s["year"] for s in load_json(os.path.join(folder, "league.json"))[0]["seasons"]
               if ((s.get("coverage") or {}).get("fixtures") or {}).get("statistics_fixtures")}
    lines.append(f"{code} · {LEAGUES[code][2]}")
    for year in years:
        fixtures = load_json(os.path.join(folder, str(year), "fixtures.json"))
        stats: dict[int, list] = {}
        sp = os.path.join(folder, str(year), "statistics.jsonl")
        if os.path.exists(sp):
            with open(sp, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        stats[row["fixture"]] = row["response"]
        finished = [f for f in fixtures if f["fixture"]["status"]["short"] in FINISHED]
        empty = sum(1 for f in finished if f["fixture"]["id"] in stats and not stats[f["fixture"]["id"]])
        if year in covered:
            missing += sum(1 for f in finished if f["fixture"]["id"] not in stats)
        rounds = Counter(str(f["league"].get("round", "")).rsplit(" - ", 1)[0] for f in fixtures)
        lines.append(f"  {year} : {len(fixtures)} matchs, {len(finished)} terminés, "
                     + (f"{len(stats)} avec statistiques ({empty} vides) · " if year in covered
                        else "statistiques non couvertes · ")
                     + ", ".join(f"{r} ({n})" for r, n in rounds.most_common()))
summary = os.path.join(out, "RESUME.txt")
with open(summary, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
archive = os.path.expanduser(f"~/storage/downloads/api-football-historique-{date.today():%Y%m%d}.tar.gz")
with tarfile.open(archive, "w:gz") as tar:
    tar.add(out, arcname="api-football-historique")
print("\n".join(lines[3:]))
print(f"\nArchive prête ({os.path.getsize(archive) / 1e6:.1f} Mo) : {archive}")
print(f"Requêtes utilisées : {used} · restantes aujourd'hui : {remaining if remaining is not None else '?'}")
if stopped or missing:
    print(f"Il reste {missing} matchs sans statistiques : relancer la même commande demain "
          "(reprise automatique), ou envoyer déjà cette archive pour commencer l'étude.")
PY
