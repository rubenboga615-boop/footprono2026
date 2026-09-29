#!/usr/bin/env bash
# Installation de FootProno dans Termux natif. Idempotent : peut être relancé
# après une mise à jour du dépôt.
#   bash scripts/termux/setup.sh         # ce qu'il faut pour faire tourner le serveur
#   bash scripts/termux/setup.sh --dev   # + outils de test (pytest, mypy, ruff)
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

DEV=0
[ "${1:-}" = "--dev" ] && DEV=1

log "Paquets Termux"
PACKAGES=(python postgresql redis clang rust binutils libffi openssl git)
# ruff (vérification du code) est fourni précompilé par Termux : le compiler
# avec pip prendrait des heures sur téléphone.
[ "$DEV" = 1 ] && PACKAGES+=(ruff)
pkg install -y "${PACKAGES[@]}"

log "PostgreSQL dédié ($PGDATA, port $PG_PORT)"
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

log "Redis dédié (port $REDIS_PORT)"
start_redis

log "Environnement Python ($(python --version))"
if [ ! -x "$VENV/bin/python" ]; then
    python -m venv "$VENV"
fi
# Aucun paquet précompilé n'existe pour Android sur PyPI : pip compile
# pydantic-core (Rust), asyncpg, greenlet et markupsafe (C). Les paquets
# compilés sont gardés dans le cache de pip : une relance ne recompile rien.
# maturin (pydantic-core) a besoin du niveau d'API Android.
ANDROID_API_LEVEL="$(getprop ro.build.version.sdk 2>/dev/null || echo 24)"
export ANDROID_API_LEVEL
# Compilation Rust plus rapide et moins gourmande en mémoire (sans LTO).
export CARGO_PROFILE_RELEASE_LTO=off CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16
"$VENV/bin/pip" install --upgrade pip
if [ "$DEV" = 1 ]; then
    LOCK="$BACKEND/requirements-test.lock"
else
    LOCK="$BACKEND/requirements.lock"
fi
log "Installation des dépendances ($(basename "$LOCK"))"
log "La première fois, la compilation de pydantic-core (Rust) prend plusieurs minutes : c'est normal."
"$VENV/bin/pip" install -r "$LOCK"
"$VENV/bin/pip" install --no-deps -e "$BACKEND"

cd "$BACKEND"
if [ ! -f .env ]; then
    cp .env.example .env
    log "backend/.env créé à partir de .env.example"
fi
# Les adresses de la base et de Redis suivent toujours la configuration des scripts.
sed -i \
    -e "s|^FP_DATABASE_URL=.*|FP_DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@127.0.0.1:$PG_PORT/$DB_NAME|" \
    -e "s|^FP_REDIS_URL=.*|FP_REDIS_URL=redis://127.0.0.1:$REDIS_PORT/0|" \
    .env

log "Migrations"
load_env
migrate

log "Installation terminée. Démarrage : bash scripts/termux/start.sh"
