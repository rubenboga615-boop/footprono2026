#!/usr/bin/env bash
# Ingestion des données (football-data, Understat, API-Football) et contrôles de qualité.
#   bash scripts/termux/ingest.sh all                        # historique complet (2016 → saison en cours)
#   bash scripts/termux/ingest.sh all --seasons 2026         # saison en cours seulement
#   bash scripts/termux/ingest.sh football-data --from-dir ~/footprono-data/football-data
#   bash scripts/termux/ingest.sh quality                    # contrôles seuls
#   bash scripts/termux/ingest.sh odds                       # cotes des matchs à venir
#   bash scripts/termux/ingest.sh live                       # matchs en cours (score, fin, statistiques)
#   bash scripts/termux/ingest.sh injuries                   # blessés et suspendus d'aujourd'hui et demain
# Options : bash scripts/termux/ingest.sh --help
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -x "$VENV/bin/footprono-ingest" ] || die "commande absente : relancer bash scripts/termux/setup.sh"
# Une seule collecte d'historique à la fois : deux en parallèle consomment deux fois
# le quota. Les commandes courtes (odds, live, injuries, quality) restent possibles.
HEAVY='bin/footprono-ingest (all|football-data|understat|api-football)'
case "${1:-}" in
    all|football-data|understat|api-football)
        if running=$(pgrep -f "$HEAVY" 2>/dev/null); then
            die "une collecte tourne déjà (processus : $(echo "$running" | tr '\n' ' ')). Suivre : tail -f ~/ingest-api.log ; arrêter : bash scripts/termux/stop-ingest.sh"
        fi
        ;;
esac
start_postgres
load_env
migrate
exec "$VENV/bin/footprono-ingest" "$@"
