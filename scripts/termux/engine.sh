#!/usr/bin/env bash
# Moteur de prédiction : backtest (évaluation stricte dans le temps).
#   bash scripts/termux/engine.sh backtest                     # saisons 2022-23 → 2025-26
#   bash scripts/termux/engine.sh backtest --seasons 2024-2025 --competitions LIGUE_1
#   bash scripts/termux/engine.sh features                     # gain de chaque indicateur de contexte
#   bash scripts/termux/engine.sh counts                       # corners, cartons, tirs
#   bash scripts/termux/engine.sh ah                           # handicap asiatique contre les cotes
# Options : bash scripts/termux/engine.sh backtest --help
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -x "$VENV/bin/footprono-engine" ] || die "commande absente : relancer bash scripts/termux/setup.sh"
start_postgres
load_env
migrate
exec "$VENV/bin/footprono-engine" "$@"
