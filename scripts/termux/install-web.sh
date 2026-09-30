#!/usr/bin/env bash
# Installe la version web de l'application (archive « footprono-web » téléchargée
# depuis GitHub Actions) : l'API la sert ensuite sur http://127.0.0.1:8000/app/
#   bash scripts/termux/install-web.sh ~/storage/downloads/footprono-web.zip
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

ZIP="${1:-}"
[ -f "$ZIP" ] || die "archive introuvable : $ZIP
Télécharger « footprono-web » (GitHub > Actions > Application > Artifacts), puis :
  termux-setup-storage   # une fois, pour accéder aux Téléchargements
  bash scripts/termux/install-web.sh ~/storage/downloads/footprono-web.zip"
command -v unzip >/dev/null 2>&1 || pkg install -y unzip

WEB="$FP_DATA/web"
rm -rf "$WEB.new"
mkdir -p "$WEB.new"
unzip -q "$ZIP" -d "$WEB.new"
[ -f "$WEB.new/index.html" ] || die "index.html absent de l'archive : est-ce bien « footprono-web » ?"
rm -rf "$WEB"
mv "$WEB.new" "$WEB"

cd "$BACKEND"
grep -q '^FP_WEB_APP_DIR=' .env || echo 'FP_WEB_APP_DIR=' >> .env
sed -i "s|^FP_WEB_APP_DIR=.*|FP_WEB_APP_DIR=$WEB|" .env
log "Version web installée dans $WEB"
log "Redémarrer l'API : bash scripts/termux/stop.sh && bash scripts/termux/start.sh"
log "Puis ouvrir http://127.0.0.1:$PORT/app/ dans le navigateur du téléphone"
