#!/usr/bin/env bash
# Transfère FootProba de Termux vers le serveur : base complète (comptes,
# paris, données collectées), clé Firebase et clé API-Football.
#   bash scripts/termux/send-to-server.sh <ip du serveur>
# Le serveur doit être installé (deploy/install-server.sh). La base du serveur
# est remplacée (sauvegardée avant). Termux n'est pas modifié.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

HOST="${1:-}"
[ -n "$HOST" ] || die "usage : bash scripts/termux/send-to-server.sh <ip du serveur>"
command -v ssh >/dev/null 2>&1 || pkg install -y openssh
REMOTE="root@$HOST"
DEPLOY=/opt/footprono/deploy

ssh -o ConnectTimeout=15 "$REMOTE" "test -f $DEPLOY/.env" \
    || die "serveur injoignable ou pas installé (lancer d'abord install-server.sh dessus)"

start_postgres
DUMP="$RUN/footprono-termux-$(date -u +%Y%m%d-%H%M).dump"
log "Sauvegarde de la base Termux"
pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc -f "$DUMP"
log "$(du -h "$DUMP" | cut -f1) à envoyer"

log "Envoi au serveur"
scp "$DUMP" "$REMOTE:$DEPLOY/backups/"
if [ -f "$FP_DATA/firebase-service-account.json" ]; then
    scp "$FP_DATA/firebase-service-account.json" "$REMOTE:$DEPLOY/secrets/firebase.json"
    ssh "$REMOTE" "chmod 755 $DEPLOY/secrets && chmod 644 $DEPLOY/secrets/firebase.json && \
        sed -i 's|^FP_FCM_CREDENTIALS_FILE=.*|FP_FCM_CREDENTIALS_FILE=/secrets/firebase.json|' $DEPLOY/.env"
else
    log "Pas de clé Firebase sur Termux : notifications push non configurées sur le serveur"
fi
key="$(grep -E '^FP_API_FOOTBALL_KEY=' "$BACKEND/.env" | cut -d= -f2- || true)"
if [ -n "$key" ]; then
    printf '%s\n' "$key" | ssh "$REMOTE" \
        "read -r k && sed -i \"s|^FP_API_FOOTBALL_KEY=.*|FP_API_FOOTBALL_KEY=\$k|\" $DEPLOY/.env"
fi

log "Restauration sur le serveur"
ssh "$REMOTE" "bash $DEPLOY/restore.sh $DEPLOY/backups/$(basename "$DUMP") --oui"
rm -f "$DUMP"

log "Transfert terminé."
echo "Vérifier dans l'application (Profil → Serveur : l'adresse https du serveur), puis"
echo "arrêter le serveur Termux pour ne pas collecter deux fois (quota API-Football) :"
echo "  bash scripts/termux/stop.sh"
