#!/usr/bin/env bash
# Active les notifications push : installe la clé du compte de service Firebase
# (Paramètres du projet → Comptes de service → Générer une nouvelle clé privée).
#   bash scripts/termux/install-firebase.sh ~/storage/downloads/footprono-56616-xxxx.json
# La clé est secrète : elle est copiée hors du dépôt (lisible par Termux seul),
# puis le fichier téléchargé peut être supprimé.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

KEY="${1:-}"
[ -f "$KEY" ] || die "clé introuvable : $KEY
Télécharger la clé (console Firebase → Paramètres du projet → Comptes de service
→ Générer une nouvelle clé privée), puis :
  termux-setup-storage   # une fois, pour accéder aux Téléchargements
  bash scripts/termux/install-firebase.sh ~/storage/downloads/<fichier>.json"
[ -x "$VENV/bin/python" ] || die "lancer d'abord setup.sh"

# Contrôle : vraie clé de compte de service (pas google-services.json).
"$VENV/bin/python" - "$KEY" <<'PY' || die "fichier refusé (voir ci-dessus)"
import sys
from pathlib import Path
from footprono.notifications.push import PushConfigError, ServiceAccount
try:
    account = ServiceAccount.load(Path(sys.argv[1]))
except PushConfigError as exc:
    print(f"Clé refusée : {exc}", file=sys.stderr)
    sys.exit(1)
print(f"Projet Firebase : {account.project_id} ({account.client_email})")
PY

DEST="$FP_DATA/firebase-service-account.json"
mkdir -p "$FP_DATA"
install -m 600 "$KEY" "$DEST"

cd "$BACKEND"
grep -q '^FP_FCM_CREDENTIALS_FILE=' .env || echo 'FP_FCM_CREDENTIALS_FILE=' >> .env
sed -i "s|^FP_FCM_CREDENTIALS_FILE=.*|FP_FCM_CREDENTIALS_FILE=$DEST|" .env
log "Clé installée dans $DEST (lisible par Termux seul)"
log "Supprimer le fichier téléchargé : rm \"$KEY\""
log "Redémarrer : bash scripts/termux/stop.sh && bash scripts/termux/start.sh"
log "Essai : bash scripts/termux/admin.sh push-test <ton numéro>"
