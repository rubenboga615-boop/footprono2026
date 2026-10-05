#!/usr/bin/env bash
# Publie une nouvelle version de l'application : les téléphones la proposent à l'ouverture.
#   bash scripts/termux/publish-apk.sh "Nouveautés…"                  # archive la plus récente des Téléchargements
#   bash scripts/termux/publish-apk.sh "Correctif important" --minimum 45   # obligatoire sous 45
#   bash scripts/termux/publish-apk.sh --archive CHEMIN.zip "Nouveautés…"   # archive précise
#   FP_SERVEUR=62.238.116.74 bash scripts/termux/publish-apk.sh "Nouveautés…"  # sur le serveur distant
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
"$VENV/bin/python" -m zipfile -t "$archive" >/dev/null 2>&1 \
    || die "archive abîmée (téléchargement incomplet ?) : la retélécharger depuis GitHub Actions"
if [ -n "${FP_SERVEUR:-}" ]; then
    # Serveur distant (Docker) : l'archive est copiée sur le serveur puis dans le
    # conteneur de l'API ; les notes voyagent en base64 (accents, guillemets sans risque).
    command -v ssh >/dev/null 2>&1 || pkg install -y openssh
    for a in "$@"; do
        case "$a" in *[!A-Za-z0-9._-]*) die "option non prise en charge sur le serveur : $a";; esac
    done
    notes64="$(printf %s "$notes" | base64 | tr -d '\n')"
    compose='docker compose -f docker-compose.yml --env-file .env'
    # Copie par scp (vérifiée), puis dans le conteneur (« docker compose cp ») : un envoi
    # par l'entrée standard de « docker compose exec » abîmait l'archive.
    sum="$(sha256sum "$archive" | cut -d' ' -f1)"
    scp -q "$archive" "root@$FP_SERVEUR:/tmp/footprono-apk.zip"
    inner='footprono-admin publish-apk /tmp/apk.zip --notes "$(echo "$FP_NOTES" | base64 -d)" '"$*"
    ssh "root@$FP_SERVEUR" "set -e; cd /opt/footprono/deploy
        echo '$sum  /tmp/footprono-apk.zip' | sha256sum -c --quiet
        $compose cp /tmp/footprono-apk.zip api:/tmp/apk.zip
        $compose exec -T -u root api chown app:app /data/app /tmp/apk.zip
        s=0; $compose exec -T -e FP_NOTES=$notes64 api sh -c '$inner' || s=\$?
        $compose exec -T -u root api rm -f /tmp/apk.zip; rm -f /tmp/footprono-apk.zip
        exit \$s"
else
    load_env
    "$VENV/bin/footprono-admin" publish-apk "$archive" --notes "$notes" "$@"
fi
echo "Les anciennes archives peuvent être supprimées : rm ~/storage/downloads/footprono-apk*.zip"
