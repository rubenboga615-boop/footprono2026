# Fonctions partagées par les scripts Termux (Termux natif, pas proot/Ubuntu).
# shellcheck shell=bash

if [ -z "${PREFIX:-}" ] || ! command -v pkg >/dev/null 2>&1; then
    echo "Ces scripts se lancent dans Termux natif (pas dans Ubuntu/proot)." >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
RUN="${FP_RUN_DIR:-$ROOT/.run}"
PORT="${FP_PORT:-8000}"

# Instances DÉDIÉES à FootProno (dossier et ports propres) : un PostgreSQL ou
# un Redis déjà utilisé par d'autres projets Termux n'est jamais touché.
FP_DATA="${FP_DATA_DIR:-$PREFIX/var/lib/footprono}"
PGDATA="${FP_PGDATA:-$FP_DATA/postgresql}"
PG_PORT="${FP_PG_PORT:-5433}"
DB_NAME="${FP_DB_NAME:-footprono}"
DB_USER="${FP_DB_USER:-footprono}"
DB_PASSWORD="${FP_DB_PASSWORD:-footprono}"
REDIS_PORT="${FP_REDIS_PORT:-6380}"
REDIS_DIR="$FP_DATA/redis"

# Socket PostgreSQL explicite dans $PREFIX/tmp (défaut de Termux) : psql et
# pg_ctl la trouvent sans dépendre des options de compilation.
PG_SOCKET_DIR="$PREFIX/tmp"
export PGPORT="$PG_PORT" PGHOST="$PG_SOCKET_DIR"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mErreur :\033[0m %s\n' "$*" >&2; exit 1; }

pg_running() { pg_ctl -D "$PGDATA" status >/dev/null 2>&1; }

start_postgres() {
    [ -f "$PGDATA/PG_VERSION" ] || die "PostgreSQL non initialisé (lancer setup.sh)"
    if ! pg_running; then
        if pg_isready -q -h 127.0.0.1 -p "$PG_PORT" 2>/dev/null; then
            die "le port $PG_PORT est déjà utilisé par un autre PostgreSQL.
Choisis un autre port : FP_PG_PORT=5434 bash scripts/termux/setup.sh"
        fi
        mkdir -p "$PG_SOCKET_DIR"
        pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" -w \
            -o "-p $PG_PORT -k $PG_SOCKET_DIR -c listen_addresses=127.0.0.1" start
    fi
}

start_redis() {
    if ! redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
        mkdir -p "$REDIS_DIR"
        redis-server --port "$REDIS_PORT" --bind 127.0.0.1 --daemonize yes \
            --dir "$REDIS_DIR" --logfile "$REDIS_DIR/redis.log" --appendonly yes
        for _ in 1 2 3 4 5; do
            redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1 && return
            sleep 1
        done
        die "Redis ne répond pas sur le port $REDIS_PORT (voir $REDIS_DIR/redis.log)"
    fi
}

load_env() {
    cd "$BACKEND"
    [ -f .env ] || die "backend/.env absent (lancer setup.sh)"
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
}

migrate() {
    "$VENV/bin/alembic" -c "$BACKEND/alembic.ini" upgrade head
}
