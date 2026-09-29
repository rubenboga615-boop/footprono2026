#!/usr/bin/env bash
# Installation de FootProno sur Ubuntu/Debian (y compris Ubuntu dans Termux).
# Idempotent : peut être relancé après une mise à jour du dépôt.
#   bash scripts/local/setup.sh
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

require_debian_like

log "Paquets système"
as_root apt-get update -qq
as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    postgresql redis-server curl ca-certificates git build-essential

log "PostgreSQL"
VERSION="$(pg_version)"
if ! pg_lsclusters -h | awk -v v="$VERSION" '$1 == v && $2 == "main"' | grep -q .; then
    as_root pg_createcluster "$VERSION" main
fi
# Sous proot (Ubuntu dans Termux), la mémoire partagée POSIX n'est pas
# disponible : PostgreSQL doit utiliser mmap. Sans effet négatif ailleurs.
as_root pg_conftool "$VERSION" main set dynamic_shared_memory_type mmap
if pg_online; then
    as_root pg_ctlcluster "$VERSION" main restart
else
    as_root pg_ctlcluster "$VERSION" main start
fi
PGPORT="$(pg_port)"

psql_admin() { as_postgres psql -p "$PGPORT" -v ON_ERROR_STOP=1 -qtA "$@"; }
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

log "Python 3.12 et dépendances (uv)"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
cd "$BACKEND"
# uv fournit Python 3.12 même si la distribution en a une autre version.
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv -r requirements-dev.lock
uv pip install --python .venv --no-deps -e .

if [ ! -f .env ]; then
    cp .env.example .env
    sed -i \
        -e "s|^FP_DATABASE_URL=.*|FP_DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@127.0.0.1:$PGPORT/$DB_NAME|" \
        -e "s|^FP_REDIS_URL=.*|FP_REDIS_URL=redis://127.0.0.1:$REDIS_PORT/0|" \
        .env
    log "backend/.env créé à partir de .env.example"
fi

log "Migrations"
load_env
.venv/bin/alembic upgrade head

log "Installation terminée. Démarrage : bash scripts/local/start.sh"
