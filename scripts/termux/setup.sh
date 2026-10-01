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
# numpy et scipy (moteur de prédiction) sont fournis précompilés par Termux :
# pip ne sait pas les compiler raisonnablement sur téléphone (Fortran, BLAS).
# cryptography (clé Firebase des notifications push) aussi : sa compilation
# Rust prendrait très longtemps.
PACKAGES=(python python-numpy python-scipy python-cryptography postgresql redis clang rust binutils libffi openssl git)
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
# Le rôle et les bases existent déjà si l'application s'y connecte (TCP, avec
# mot de passe) : rien à créer, et la socket locale n'est pas nécessaire.
app_db_ok() { PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -U "$DB_USER" -d "$1" -qtAc "SELECT 1" >/dev/null 2>&1; }
if app_db_ok "$DB_NAME" && app_db_ok "${DB_NAME}_test"; then
    echo "rôle $DB_USER et bases déjà en place"
else
    [ -S "$PG_SOCKET_DIR/.s.PGSQL.$PG_PORT" ] || die "socket PostgreSQL absente ($PG_SOCKET_DIR/.s.PGSQL.$PG_PORT) alors que le serveur tourne.
Redémarrer PostgreSQL puis relancer : bash scripts/termux/stop.sh --all && bash scripts/termux/setup.sh"
    psql_admin() { psql -d postgres -v ON_ERROR_STOP=1 -qtA "$@"; }
    if [ "$(psql_admin -c "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'")" != "1" ]; then
        psql_admin -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD' CREATEDB"
    fi
    for db in "$DB_NAME" "${DB_NAME}_test"; do
        if [ "$(psql_admin -c "SELECT 1 FROM pg_database WHERE datname = '$db'")" != "1" ]; then
            psql_admin -c "CREATE DATABASE $db OWNER $DB_USER"
        fi
    done
fi

log "Redis dédié (port $REDIS_PORT)"
start_redis

log "Environnement Python ($(python --version))"
if [ ! -x "$VENV/bin/python" ]; then
    python -m venv "$VENV"
fi
# Le venv voit les paquets Python de Termux (numpy, scipy précompilés).
sed -i 's/^include-system-site-packages = false/include-system-site-packages = true/' "$VENV/pyvenv.cfg"
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
mkdir -p "$RUN"
grep -vE '^(numpy|scipy|cryptography)==' "$LOCK" > "$RUN/requirements-termux.txt"
"$VENV/bin/pip" install -r "$RUN/requirements-termux.txt"
"$VENV/bin/pip" install --no-deps -e "$BACKEND"
"$VENV/bin/python" -c "import numpy, scipy, cryptography; print('numpy', numpy.__version__, '· scipy', scipy.__version__, '· cryptography', cryptography.__version__)" \
    || die "numpy, scipy ou cryptography introuvable : pkg install python-numpy python-scipy python-cryptography"

cd "$BACKEND"
if [ ! -f .env ]; then
    cp .env.example .env
    log "backend/.env créé à partir de .env.example"
fi
# Les adresses de la base et de Redis, et le dossier des fichiers bruts,
# suivent toujours la configuration des scripts.
grep -q '^FP_RAW_DATA_DIR=' .env || echo 'FP_RAW_DATA_DIR=' >> .env
sed -i \
    -e "s|^FP_DATABASE_URL=.*|FP_DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@127.0.0.1:$PG_PORT/$DB_NAME|" \
    -e "s|^FP_REDIS_URL=.*|FP_REDIS_URL=redis://127.0.0.1:$REDIS_PORT/0|" \
    -e "s|^FP_RAW_DATA_DIR=.*|FP_RAW_DATA_DIR=$RAW_DIR|" \
    .env
# Clé secrète des jetons de connexion : générée une fois, jamais remplacée ensuite
# (la changer déconnecterait tous les utilisateurs).
if ! grep -qE '^FP_SECRET_KEY=.{32,}' .env; then
    secret=$("$VENV/bin/python" -c "import secrets; print(secrets.token_urlsafe(48))")
    grep -q '^FP_SECRET_KEY=' .env || echo 'FP_SECRET_KEY=' >> .env
    sed -i "s|^FP_SECRET_KEY=.*|FP_SECRET_KEY=$secret|" .env
    log "FP_SECRET_KEY générée"
fi

log "Migrations"
load_env
migrate

log "Installation terminée. Démarrage : bash scripts/termux/start.sh"
