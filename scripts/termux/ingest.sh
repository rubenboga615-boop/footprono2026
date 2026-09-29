#!/usr/bin/env bash
# Ingestion des données (football-data, Understat) et contrôles de qualité.
#   bash scripts/termux/ingest.sh all                        # historique complet (2016 → saison en cours)
#   bash scripts/termux/ingest.sh all --seasons 2026         # saison en cours seulement
#   bash scripts/termux/ingest.sh football-data --from-dir ~/footprono-data/football-data
#   bash scripts/termux/ingest.sh quality                    # contrôles seuls
# Options : bash scripts/termux/ingest.sh --help
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -x "$VENV/bin/footprono-ingest" ] || die "commande absente : relancer bash scripts/termux/setup.sh"
start_postgres
load_env
migrate
exec "$VENV/bin/footprono-ingest" "$@"
