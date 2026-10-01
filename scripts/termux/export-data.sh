#!/usr/bin/env bash
# Exporte les données football (matchs, statistiques, cotes, prédictions) pour
# les études du moteur, SANS données personnelles : comptes, portefeuilles,
# paris, montantes, notifications, appareils, paiements et abonnements sont
# exportés vides (structure seulement).
#   bash scripts/termux/export-data.sh
# Le fichier arrive dans les Téléchargements (termux-setup-storage une fois).
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

DEST_DIR="$HOME/storage/downloads"
[ -d "$DEST_DIR" ] || die "Téléchargements inaccessibles : lancer d'abord termux-setup-storage"
start_postgres
OUT="$DEST_DIR/footprono-donnees-$(date +%Y%m%d).dump"
PERSONAL=(users wallets wallet_entries bets bet_selections montantes montante_steps
    notifications push_devices payments subscription_events)
args=()
for t in "${PERSONAL[@]}"; do args+=(--exclude-table-data="$t"); done
log "Export des données football (sans données personnelles)…"
pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc -Z 9 "${args[@]}" -f "$OUT"
log "Fichier prêt : $OUT ($(du -h "$OUT" | cut -f1))"
