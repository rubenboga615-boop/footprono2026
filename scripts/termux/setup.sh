#!/data/data/com.termux/files/usr/bin/bash
# Installation de FootProno sur Termux (une seule fois, ou après mise à jour).
#   bash scripts/termux/setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="$ROOT/backend"
PGDATA="${FP_PGDATA:-$PREFIX/var/lib/postgresql}"
DB_NAME="${FP_DB_NAME:-footprono}"
DB_USER="${FP_DB_USER:-footprono}"
DB_PASSWORD="${FP_DB_PASSWORD:-footprono}"

echo "==> Paquets système"
pkg install -y python postgresql redis clang rust binutils libffi openssl

echo "==> PostgreSQL"
if [ ! -d "$PGDATA" ]; then
    mkdir -p "$PGDATA"
    initdb -D "$PGDATA" --auth=scram-sha-256 --username="$(whoami)" --pwfile=<(echo "$DB_PASSWORD")
fi
if ! pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
    pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" start
    sleep 3
fi
export PGPASSWORD="$DB_PASSWORD"
if ! psql -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    psql -d postgres -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD' CREATEDB"
fi
for db in "$DB_NAME" "${DB_NAME}_test"; do
    if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
        psql -d postgres -c "CREATE DATABASE $db OWNER $DB_USER"
    fi
done

echo "==> Environnement Python"
cd "$BACKEND"
python -m venv .venv
# maturin (pydantic-core) a besoin du niveau d'API Android pour compiler.
ANDROID_API_LEVEL="$(getprop ro.build.version.sdk)"
export ANDROID_API_LEVEL
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/pip install --no-deps -e .

if [ ! -f .env ]; then
    cp .env.example .env
    sed -i "s|^FP_DATABASE_URL=.*|FP_DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@127.0.0.1:5432/$DB_NAME|" .env
    echo "    .env créé à partir de .env.example : vérifie-le."
fi

echo "==> Migrations"
.venv/bin/alembic upgrade head

echo "Installation terminée. Démarrage : bash scripts/termux/start.sh"
