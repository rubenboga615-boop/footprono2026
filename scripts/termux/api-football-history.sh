#!/usr/bin/env bash
# Historique d'API-Football (matchs, journées, statistiques de match : tirs, corners…)
# pour étudier de nouvelles compétitions AVANT de les ajouter à l'application :
# championnats, coupes d'Europe des clubs, compétitions de sélections nationales.
# Rien n'est chargé dans la base : les fichiers sont rangés puis réunis dans une
# archive à envoyer pour l'étude. Aucune donnée personnelle ; la clé API est lue dans
# backend/.env et n'est jamais écrite ni affichée.
#
#   bash scripts/termux/api-football-history.sh               # TOUT, par ordre de priorité
#   bash scripts/termux/api-football-history.sh NOR SWE AUS   # compétitions au choix
#   bash scripts/termux/api-football-history.sh COUPES        # groupe : CLUBS, COUPES ou SELECTIONS
#   FP_AF_FROM=2016 bash scripts/termux/api-football-history.sh   # depuis 2016 (défaut 2018)
#   FP_AF_RESERVE=3000 bash scripts/termux/api-football-history.sh  # requêtes laissées au serveur
#
# Coût : 1 requête par saison pour la liste des matchs, puis 1 par match terminé pour
# ses statistiques (environ 250 par saison de championnat). Coupes d'Europe : statistiques
# de la phase principale seulement (pas des tours préliminaires) ; sélections nationales :
# résultats seulement (la liste des matchs suffit, aucune statistique demandée). Le script s'arrête de lui-même quand il ne
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

# code : (identifiant API-Football, pays chez API-Football, nom affiché, statistiques,
#         mot attendu dans le nom chez API-Football)
# statistiques : "all" tous les matchs terminés, "main" hors tours préliminaires et de
# qualification, "none" aucune (résultats seulement). L'ordre est l'ordre de priorité.
CLUBS = {
    "SWZ": (207, "Switzerland", "Suisse · Super League", "all", ""),
    "NOR": (103, "Norway", "Norvège · Eliteserien", "all", ""),
    "SWE": (113, "Sweden", "Suède · Allsvenskan", "all", ""),
    "DNK": (119, "Denmark", "Danemark · Superliga", "all", ""),
    "AUT": (218, "Austria", "Autriche · Bundesliga", "all", ""),
    "POL": (106, "Poland", "Pologne · Ekstraklasa", "all", ""),
    "ROU": (283, "Romania", "Roumanie · Liga I", "all", ""),
    "AUS": (188, "Australia", "Australie · A-League", "all", ""),
    "CZE": (345, "Czech-Republic", "Tchéquie · 1re division", "all", ""),
    "CRO": (210, "Croatia", "Croatie · HNL", "all", ""),
    "SRB": (286, "Serbia", "Serbie · Super Liga", "all", ""),
    "ISR": (383, "Israel", "Israël · Ligat ha'Al", "all", ""),
    "CYP": (318, "Cyprus", "Chypre · 1re division", "all", ""),
}
COUPES = {
    "UCL": (2, "World", "Ligue des Champions", "main", "champions league"),
    "UEL": (3, "World", "Europa League", "main", "europa league"),
    "UECL": (848, "World", "Conférence League", "main", "conference league"),
}
SELECTIONS = {
    "CAN": (6, "World", "Coupe d'Afrique des Nations", "none", "africa cup of nations"),
    "CANQ": (36, "World", "CAN · éliminatoires", "none", "qualification"),
    "WC": (1, "World", "Coupe du Monde", "none", "world cup"),
    "WCQ_AFR": (29, "World", "Coupe du Monde · éliminatoires Afrique", "none", "africa"),
    "WCQ_EUR": (32, "World", "Coupe du Monde · éliminatoires Europe", "none", "europe"),
    "WCQ_SAM": (34, "World", "Coupe du Monde · éliminatoires Amérique du Sud", "none", "south america"),
    "EURO": (4, "World", "Euro", "none", "euro"),
    "EUROQ": (960, "World", "Euro · éliminatoires", "none", "qualification"),
    "UNL": (5, "World", "Ligue des Nations", "none", "nations league"),
    "COPA": (9, "World", "Copa América", "none", "copa america"),
    "AMICAL": (10, "World", "Matchs amicaux", "none", "friendlies"),
}
LEAGUES = {**CLUBS, **COUPES, **SELECTIONS}
GROUPS = {"CLUBS": CLUBS, "COUPES": COUPES, "SELECTIONS": SELECTIONS, "TOUT": LEAGUES}
PRELIMINARY = ("qualif", "preliminary")


def wants_stats(code: str, item: dict) -> bool:
    """Statistiques demandées pour ce match terminé ?"""
    mode = LEAGUES[code][3]
    if mode == "none":
        return False
    rnd = str(item["league"].get("round", "")).lower()
    return mode == "all" or not any(word in rnd for word in PRELIMINARY)


FINISHED = {"FT", "AET", "PEN"}

key = os.environ.get("FP_API_FOOTBALL_KEY")
if not key:
    sys.exit("FP_API_FOOTBALL_KEY absente de backend/.env")
requested = [a.upper() for a in sys.argv[1:]] or ["TOUT"]
unknown = [a for a in requested if a not in LEAGUES and a not in GROUPS]
if unknown:
    sys.exit(f"Inconnu : {', '.join(unknown)}. Choix possibles : {', '.join([*GROUPS, *LEAGUES])}")
args = list(dict.fromkeys(c for a in requested for c in (GROUPS[a] if a in GROUPS else [a])))
first = int(os.environ.get("FP_AF_FROM", "2018"))
reserve = int(os.environ.get("FP_AF_RESERVE", "1500"))
current = current_season_start()
# Saisons sur l'année civile (Norvège, Suède, sélections) : jusqu'à l'année en cours.
last = max(current, date.today().year)
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
        league_id, country, label, mode, hint = LEAGUES[code]
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
        name = info[0]["league"]["name"]
        wrong_country = got.replace("-", " ").lower() != country.replace("-", " ").lower()
        if wrong_country or hint not in name.lower():
            print(f"\n== {code} : l'identifiant {league_id} est « {got} · {name} », "
                  f"pas « {label} » : ignoré (à signaler)")
            continue
        print(f"\n== {code} · {got} · {info[0]['league']['name']}", flush=True)
        seasons = {s["year"]: s for s in info[0]["seasons"]}
        for year in range(first, last + 1):
            s = seasons.get(year)
            if s is None:
                if year <= current:  # pas d'édition cette année-là (Euro, CAN, Coupe du Monde…)
                    print(f"  {year} : pas de saison chez API-Football")
                continue
            covered = bool(((s.get("coverage") or {}).get("fixtures") or {}).get("statistics_fixtures"))
            stats_ok = covered and mode != "none"
            path = os.path.join(out, code, str(year), "fixtures.json")
            if not os.path.exists(path) or year >= current - 1:
                save_json(path, get("/fixtures", league=league_id, season=year))
            fixtures = load_json(path)
            finished = sum(1 for f in fixtures if f["fixture"]["status"]["short"] in FINISHED)
            wanted = "résultats seulement" if mode == "none" else f"statistiques {'oui' if covered else 'non'}"
            print(f"  {year} : {len(fixtures)} matchs, {finished} terminés · {wanted}", flush=True)
            plan.append((code, year, stats_ok))

    # 2. Statistiques de chaque match terminé (1 requête par match).
    todo = 0
    for code, year, stats_ok in plan:
        if stats_ok:
            fixtures = load_json(os.path.join(out, code, str(year), "fixtures.json"))
            done = done_ids(os.path.join(out, code, str(year), "statistics.jsonl"))
            todo += sum(1 for f in fixtures if f["fixture"]["status"]["short"] in FINISHED
                        and f["fixture"]["id"] not in done and wants_stats(code, f))
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
                   if f["fixture"]["status"]["short"] in FINISHED and f["fixture"]["id"] not in done
                   and wants_stats(code, f)]
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
lines = [f"API-Football, téléchargé le {date.today():%d/%m/%Y}, saisons {first}-{last}",
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
               if ((s.get("coverage") or {}).get("fixtures") or {}).get("statistics_fixtures")
               and LEAGUES[code][3] != "none"}
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
            missing += sum(1 for f in finished if f["fixture"]["id"] not in stats and wants_stats(code, f))
        rounds = Counter(str(f["league"].get("round", "")).rsplit(" - ", 1)[0] for f in fixtures)
        lines.append(f"  {year} : {len(fixtures)} matchs, {len(finished)} terminés, "
                     + (f"{len(stats)} avec statistiques ({empty} vides) · " if year in covered
                        else "résultats seulement · " if LEAGUES[code][3] == "none"
                        else "statistiques non couvertes · ")
                     + ", ".join(f"{r} ({n})" for r, n in rounds.most_common(8)))
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
