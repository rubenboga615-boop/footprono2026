#!/usr/bin/env bash
# Installation de FootProno dans Termux natif. Idempotent : peut être relancé
# après une mise à jour du dépôt.
#   bash scripts/termux/setup.sh
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

log "Paquets Termux"
pkg install -y python postgresql redis clang rust binutils libffi openssl git

log "PostgreSQL"
if [ ! -f "$PGDATA/PG_VERSION" ]; then
    mkdir -p "$PGDATA"
    # Socket local sans mot de passe (utilisateur Termux uniquement),
    # connexions TCP (l'application) avec mot de passe.
    initdb -D "$PGDATA" --auth-local=trust --auth-host=scram-sha-256 -E UTF8
fi
start_postgres
psql_admin() { psql -d postgres -v ON_ERROR_STOP=1 -qtA "$@"; }
if [ "$(psql_admin -c "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'")" != "1" ]; then
    psql_admin -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD' CREATEDB"
fi
for db in "$DB_NAME" "${DB_NAME}_test"; do
    if [ "$(psql_admin -c "SELECT 1 FROM pg_database WHERE datname = '$db'")" != "1" ]; then
        psql_admin -c "CREATE DATABASE $db OWNER $DB_USER"
    fi
done

log "Redis"
start_redis

log "Environnement Python ($(python --version))"
if [ ! -x "$VENV/bin/python" ]; then
    python -m venv "$VENV"
fi
# maturin (compilation de pydantic-core) a besoin du niveau d'API Android.
ANDROID_API_LEVEL="$(getprop ro.build.version.sdk 2>/dev/null || echo 24)"
export ANDROID_API_LEVEL
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$BACKEND/requirements-dev.lock"
"$VENV/bin/pip" install --no-deps -e "$BACKEND"

cd "$BACKEND"
if [ ! -f .env ]; then
    cp .env.example .env
    sed -i \
        -e "s|^FP_DATABASE_URL=.*|FP_DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@127.0.0.1:$PG_PORT/$DB_NAME|" \
        -e "s|^FP_REDIS_URL=.*|FP_REDIS_URL=redis://127.0.0.1:$REDIS_PORT/0|" \
        .env
    log "backend/.env créé à partir de .env.example"
fi

log "Migrations"
load_env
migrate

log "Installation terminée. Démarrage : bash scripts/termux/start.sh"
