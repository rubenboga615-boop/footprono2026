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
#
# La même collecte se lance depuis la console d'administration (/admin, « Collecter
# l'historique API-Football ») : même code (backend/src/footprono/ingestion/history.py),
# même dossier, l'une reprend où l'autre s'est arrêtée.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -d "$HOME/storage/downloads" ] || die "dossier Téléchargements introuvable : lancer d'abord termux-setup-storage"
load_env
"$VENV/bin/python" - "$@" <<'PY'
import os, sys
from pathlib import Path
from footprono.ingestion import history

key = os.environ.get("FP_API_FOOTBALL_KEY")
if not key:
    sys.exit("FP_API_FOOTBALL_KEY absente de backend/.env")
groups = {**history.GROUPS, "TOUT": history.LEAGUES}
requested = [a.upper() for a in sys.argv[1:]] or ["TOUT"]
unknown = [a for a in requested if a not in history.LEAGUES and a not in groups]
if unknown:
    sys.exit(f"Inconnu : {', '.join(unknown)}. Choix possibles : {', '.join([*groups, *history.LEAGUES])}")
codes = list(dict.fromkeys(c for a in requested for c in (groups[a] if a in groups else [a])))
downloads = Path("~/storage/downloads").expanduser()
try:
    report = history.collect(
        key, codes, downloads / "api-football-historique",
        first=int(os.environ.get("FP_AF_FROM", "2018")),
        reserve=int(os.environ.get("FP_AF_RESERVE", "1500")),
        log=lambda m: print(m, flush=True),
        archive_to=downloads,
    )
except KeyboardInterrupt:
    sys.exit("\nInterrompu : ce qui est téléchargé est gardé (relancer pour reprendre).")
if report.stopped or report.missing:
    print(f"Il reste {report.missing} matchs sans statistiques : relancer la même commande demain "
          "(reprise automatique), ou envoyer déjà cette archive pour commencer l'étude.")
PY
