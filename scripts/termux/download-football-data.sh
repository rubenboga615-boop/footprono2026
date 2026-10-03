#!/usr/bin/env bash
# Téléchargement des fichiers de football-data.co.uk (résultats, statistiques, cotes),
# pour étudier de nouveaux championnats AVANT de les ajouter à l'application.
# Rien n'est chargé dans la base : les fichiers sont seulement rangés puis
# réunis dans une archive à envoyer pour l'étude. Aucune donnée personnelle,
# aucune clé : l'archive peut être partagée telle quelle.
#
#   bash scripts/termux/download-football-data.sh              # échantillon : Portugal + Belgique
#   bash scripts/termux/download-football-data.sh tout         # tous les championnats de la source
#   bash scripts/termux/download-football-data.sh P1 B1 N1     # divisions au choix
#   FP_FD_FROM=2005 bash scripts/termux/download-football-data.sh   # depuis 2005-06 (défaut 2010-11)
#
# Les fichiers déjà téléchargés sont gardés (seule la saison en cours est
# reprise) : on peut relancer après une coupure. Une pause d'une seconde
# sépare les téléchargements pour ménager le site.
# Résultat : ~/storage/downloads/football-data-<choix>-<date>.tar.gz
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -d "$HOME/storage/downloads" ] || die "dossier Téléchargements introuvable : lancer d'abord termux-setup-storage"

"$VENV/bin/python" - "$@" <<'PY'
import csv, io, os, sys, tarfile, time
from datetime import date
import httpx
from footprono.ingestion.quality import current_season_start

# Championnats « principaux » : un fichier par saison et par division,
# statistiques de match (tirs, corners, cartons) pour une partie d'entre eux.
MAIN = {
    "E0": "Angleterre Premier League", "E1": "Angleterre Championship",
    "E2": "Angleterre League One", "E3": "Angleterre League Two", "EC": "Angleterre National League",
    "SC0": "Écosse Premiership", "SC1": "Écosse Championship",
    "SC2": "Écosse League One", "SC3": "Écosse League Two",
    "D1": "Allemagne Bundesliga", "D2": "Allemagne 2. Bundesliga",
    "I1": "Italie Serie A", "I2": "Italie Serie B",
    "SP1": "Espagne Liga", "SP2": "Espagne Liga 2",
    "F1": "France Ligue 1", "F2": "France Ligue 2",
    "N1": "Pays-Bas Eredivisie", "B1": "Belgique Pro League", "P1": "Portugal Liga",
    "T1": "Turquie Süper Lig", "G1": "Grèce Super League",
}
# Autres championnats : un seul fichier par pays, toutes saisons, résultats et
# cotes (en général sans statistiques de match).
EXTRA = {
    "ARG": "Argentine", "AUT": "Autriche", "BRA": "Brésil", "CHN": "Chine",
    "DNK": "Danemark", "FIN": "Finlande", "IRL": "Irlande", "JPN": "Japon",
    "MEX": "Mexique", "NOR": "Norvège", "POL": "Pologne", "ROU": "Roumanie",
    "RUS": "Russie", "SWE": "Suède", "SWZ": "Suisse", "USA": "États-Unis",
}
SAMPLE = ["P1", "B1"]

args = [a.upper() for a in sys.argv[1:]]
if not args:
    label, main, extra = "echantillon", SAMPLE, []
elif args == ["TOUT"]:
    label, main, extra = "tout", list(MAIN), list(EXTRA)
else:
    unknown = [a for a in args if a not in MAIN and a not in EXTRA]
    if unknown:
        sys.exit(f"Inconnu : {', '.join(unknown)}. Choix possibles : {', '.join([*MAIN, *EXTRA])}")
    label, main, extra = "-".join(args).lower(), [a for a in args if a in MAIN], [a for a in args if a in EXTRA]

first = int(os.environ.get("FP_FD_FROM", "2010"))
current = current_season_start()
seasons = list(range(first, current + 1))
code = lambda y: f"{y % 100:02d}{(y + 1) % 100:02d}"  # 2026 -> « 2627 »

out = os.path.expanduser("~/storage/downloads/football-data")
os.makedirs(out, exist_ok=True)
client = httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "FootProno (etude)"})


def fetch(url: str, path: str, refresh: bool) -> tuple[str, bytes | None]:
    if os.path.exists(path) and not refresh:
        return "déjà là", open(path, "rb").read()
    for attempt in range(3):
        try:
            r = client.get(url)
        except httpx.HTTPError as e:
            if attempt == 2:
                return f"échec réseau ({type(e).__name__})", None
            time.sleep(5)
            continue
        finally:
            time.sleep(1)
        if r.status_code == 404:
            return "absent de la source", None
        if r.status_code != 200 or not r.content.strip():
            if attempt == 2:
                return f"échec HTTP {r.status_code}", None
            time.sleep(5)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(r.content)
        return "téléchargé", r.content
    return "échec", None


def describe(raw: bytes) -> str:
    """Matchs, et part des matchs avec tirs, arbitre et cotes Pinnacle."""
    text = raw.decode("utf-8-sig", errors="replace")
    rows = [r for r in csv.DictReader(io.StringIO(text)) if (r.get("HomeTeam") or r.get("Home"))]
    if not rows:
        return "0 match"
    def share(*cols: str) -> str:
        n = sum(1 for r in rows if any((r.get(c) or "").strip() for c in cols))
        return f"{100 * n // len(rows)} %"
    return (f"{len(rows)} matchs · tirs {share('HS')} · arbitre {share('Referee')} · "
            f"cotes Pinnacle {share('PSH', 'PH', 'PSCH')}")


summary = [f"football-data.co.uk, téléchargé le {date.today():%d/%m/%Y}, saisons {first}-{current}",
           "Colonnes : nombre de matchs, part avec tirs (HS), arbitre, cotes Pinnacle.", ""]
total = len(main) * len(seasons) + len(extra)
done = 0
for div in main:
    print(f"\n== {div} · {MAIN[div]}", flush=True)
    summary.append(f"{div} · {MAIN[div]}")
    for y in seasons:
        done += 1
        path = os.path.join(out, "principaux", div, f"{code(y)}.csv")
        status, raw = fetch(f"https://www.football-data.co.uk/mmz4281/{code(y)}/{div}.csv", path, y == current)
        line = f"  {y}-{(y + 1) % 100:02d} : {status}" + (f" · {describe(raw)}" if raw else "")
        print(f"[{done}/{total}]{line}", flush=True)
        summary.append(line)
for c in extra:
    done += 1
    path = os.path.join(out, "autres", f"{c}.csv")
    status, raw = fetch(f"https://www.football-data.co.uk/new/{c}.csv", path, True)
    line = f"{c} · {EXTRA[c]} : {status}" + (f" · {describe(raw)}" if raw else "")
    print(f"[{done}/{total}] {line}", flush=True)
    summary.append(line)

with open(os.path.join(out, "RESUME.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(summary) + "\n")
archive = os.path.expanduser(f"~/storage/downloads/football-data-{label}-{date.today():%Y%m%d}.tar.gz")
with tarfile.open(archive, "w:gz") as tar:
    tar.add(os.path.join(out, "RESUME.txt"), arcname="football-data/RESUME.txt")
    for div in main:
        d = os.path.join(out, "principaux", div)
        if os.path.isdir(d):
            tar.add(d, arcname=f"football-data/principaux/{div}")
    for c in extra:
        p = os.path.join(out, "autres", f"{c}.csv")
        if os.path.exists(p):
            tar.add(p, arcname=f"football-data/autres/{c}.csv")
size = os.path.getsize(archive) / 1e6
print(f"\nArchive prête ({size:.1f} Mo) : {archive}")
print("Résumé : ~/storage/downloads/football-data/RESUME.txt")
print("Envoie l'archive pour l'étude ; rien n'a été modifié dans la base de l'application.")
PY
