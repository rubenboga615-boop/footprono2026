#!/usr/bin/env bash
# Restaure une sauvegarde de la base (serveur ou export Termux) :
#   bash deploy/restore.sh deploy/backups/footprono-20261001-0300.dump [--oui]
# Arrête l'API et les workers, remplace TOUTE la base, applique les migrations,
# puis redémarre. La base actuelle est d'abord sauvegardée (avant-restauration-…).
set -euo pipefail
cd "$(dirname "$0")"
DUMP="${1:-}"
[ -f "$DUMP" ] || { echo "Usage : bash deploy/restore.sh <fichier.dump>" >&2; exit 1; }
DUMP="$(cd "$(dirname "$DUMP")" && pwd)/$(basename "$DUMP")"
compose() { docker compose -f docker-compose.yml --env-file .env "$@"; }
set -a; . ./.env; set +a

if [ "${2:-}" != "--oui" ]; then
    read -r -p "Remplacer toute la base par $(basename "$DUMP") ? (oui/non) " answer
    [ "$answer" = "oui" ] || { echo "Annulé."; exit 1; }
fi

compose stop api worker beat
safety="backups/avant-restauration-$(date -u +%Y%m%d-%H%M%S).dump"
compose exec -T postgres pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$safety"
echo "Base actuelle sauvegardée : deploy/$safety"
compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --clean --if-exists --no-owner --no-privileges < "$DUMP"
compose run --rm migrate
compose up -d api worker beat
echo "Restauration terminée."
