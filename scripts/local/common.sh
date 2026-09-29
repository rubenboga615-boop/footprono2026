# Fonctions partagées par les scripts d'exploitation locale.
# Cible : Ubuntu / Debian, y compris Ubuntu dans Termux (proot-distro).
# shellcheck shell=bash

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
RUN="${FP_RUN_DIR:-$ROOT/.run}"
PORT="${FP_PORT:-8000}"
DB_NAME="${FP_DB_NAME:-footprono}"
DB_USER="${FP_DB_USER:-footprono}"
DB_PASSWORD="${FP_DB_PASSWORD:-footprono}"
REDIS_PORT="${FP_REDIS_PORT:-6379}"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mErreur :\033[0m %s\n' "$*" >&2; exit 1; }

# Exécute une commande en root (directement si on l'est déjà, sinon via sudo).
as_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# PostgreSQL refuse de tourner en root : ses commandes passent par l'utilisateur postgres.
as_postgres() {
    if [ "$(id -u)" -eq 0 ]; then runuser -u postgres -- "$@"; else sudo -u postgres "$@"; fi
}

require_debian_like() {
    [ -r /etc/os-release ] || die "système non reconnu (/etc/os-release absent)"
    # shellcheck disable=SC1091
    . /etc/os-release
    case " ${ID:-} ${ID_LIKE:-} " in
        *" debian "* | *" ubuntu "*) ;;
        *) die "ces scripts visent Ubuntu/Debian (détecté : ${PRETTY_NAME:-inconnu})" ;;
    esac
}

# Version et port du cluster PostgreSQL « main » le plus récent.
pg_version() { find /usr/lib/postgresql -mindepth 1 -maxdepth 1 -printf '%f\n' | sort -V | tail -1; }
pg_port() { pg_lsclusters -h | awk -v v="$(pg_version)" '$1 == v && $2 == "main" { print $3 }'; }
pg_online() { pg_lsclusters -h | awk -v v="$(pg_version)" '$1 == v && $2 == "main" { print $4 }' | grep -q online; }

start_postgres() {
    local version
    version="$(pg_version)"
    [ -n "$version" ] || die "PostgreSQL n'est pas installé (lancer setup.sh)"
    if ! pg_online; then
        as_root pg_ctlcluster "$version" main start
    fi
}

start_redis() {
    if ! redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
        mkdir -p "$RUN"
        redis-server --port "$REDIS_PORT" --daemonize yes --dir "$RUN" \
            --logfile "$RUN/redis.log" --appendonly yes
        for _ in 1 2 3 4 5; do
            redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1 && return
            sleep 1
        done
        die "Redis ne répond pas (voir $RUN/redis.log)"
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
