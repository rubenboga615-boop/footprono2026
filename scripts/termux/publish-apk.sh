#!/usr/bin/env bash
# Publie une nouvelle version de l'application : les téléphones la proposent à l'ouverture.
#   bash scripts/termux/publish-apk.sh ~/storage/downloads/footprono-apk.zip "Nouveautés…"
#   bash scripts/termux/publish-apk.sh ARCHIVE "Correctif important" --minimum 45   # obligatoire sous 45
# ARCHIVE : le fichier footprono-apk.zip téléchargé depuis GitHub Actions (tel quel).
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ $# -ge 1 ] || die "usage : bash scripts/termux/publish-apk.sh ARCHIVE.zip \"nouveautés\" [--minimum N]"
archive="$1"; shift
notes="${1:-}"; [ $# -ge 1 ] && shift
[ -f "$archive" ] || die "fichier introuvable : $archive"
archive="$(realpath "$archive")"  # load_env change de dossier
load_env
exec "$VENV/bin/footprono-admin" publish-apk "$archive" --notes "$notes" "$@"
