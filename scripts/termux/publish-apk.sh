#!/usr/bin/env bash
# Publie une nouvelle version de l'application : les téléphones la proposent à l'ouverture.
#   bash scripts/termux/publish-apk.sh "Nouveautés…"                  # archive la plus récente des Téléchargements
#   bash scripts/termux/publish-apk.sh "Correctif important" --minimum 45   # obligatoire sous 45
#   bash scripts/termux/publish-apk.sh --archive CHEMIN.zip "Nouveautés…"   # archive précise
# Archive : footprono-apk.zip téléchargé depuis GitHub Actions, tel quel (Android ajoute
# « (1) », « (2) »… aux noms en double : la plus récente est prise automatiquement).
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

archive=""
if [ "${1:-}" = "--archive" ]; then
    [ $# -ge 2 ] || die "--archive demande un chemin"
    archive="$2"; shift 2
else
    archive="$(ls -t "$HOME"/storage/downloads/footprono-apk*.zip 2>/dev/null | head -1 || true)"
    [ -n "$archive" ] || die "aucune archive footprono-apk*.zip dans Téléchargements (télécharger l'APK depuis GitHub Actions)"
fi
[ -f "$archive" ] || die "fichier introuvable : $archive"
archive="$(realpath "$archive")"  # load_env change de dossier
notes="${1:-}"; [ $# -ge 1 ] && shift
echo "Archive : $archive ($(date -r "$archive" '+%d/%m %H:%M'))"
load_env
"$VENV/bin/footprono-admin" publish-apk "$archive" --notes "$notes" "$@"
echo "Les anciennes archives peuvent être supprimées : rm ~/storage/downloads/footprono-apk*.zip"
