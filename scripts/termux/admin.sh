#!/usr/bin/env bash
# Administration des comptes depuis Termux.
#   bash scripts/termux/admin.sh make-admin +22997000000      # nommer un administrateur
#   bash scripts/termux/admin.sh grant +22997000000 --days 30 # activer Premium (paiement reçu)
#   bash scripts/termux/admin.sh remove-admin +22997000000
#   bash scripts/termux/admin.sh stats
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -x "$VENV/bin/footprono-admin" ] || die "commande absente : relancer bash scripts/termux/setup.sh"
load_env
exec "$VENV/bin/footprono-admin" "$@"
