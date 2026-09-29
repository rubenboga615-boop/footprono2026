#!/data/data/com.termux/files/usr/bin/bash
# Démarre la pile complète sur Termux : PostgreSQL, Redis, API, worker, beat.
#   bash scripts/termux/start.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="$ROOT/backend"
RUN="${FP_RUN_DIR:-$ROOT/.run}"
PGDATA="${FP_PGDATA:-$PREFIX/var/lib/postgresql}"
PORT="${FP_PORT:-8000}"
mkdir -p "$RUN"

# Empêche Android de mettre les processus en veille pendant que le serveur tourne.
command -v termux-wake-lock >/dev/null && termux-wake-lock

pg_ctl -D "$PGDATA" status >/dev/null 2>&1 || pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" start
redis-cli ping >/dev/null 2>&1 || redis-server --daemonize yes --dir "$RUN" --logfile "$RUN/redis.log"

cd "$BACKEND"
set -a
# shellcheck disable=SC1091
[ -f .env ] && . ./.env
set +a

.venv/bin/alembic upgrade head

start() {
    local name="$1"; shift
    if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
        echo "$name déjà démarré (pid $(cat "$RUN/$name.pid"))"
        return
    fi
    nohup "$@" >>"$RUN/$name.log" 2>&1 &
    echo $! >"$RUN/$name.pid"
    echo "$name démarré (pid $!, logs : $RUN/$name.log)"
}

start api .venv/bin/uvicorn --factory footprono.main:create_app --host 0.0.0.0 --port "$PORT"
# Android n'offre pas les sémaphores POSIX nommés utilisés par le pool
# « prefork » : sur Termux, le worker utilise un pool de threads.
start worker .venv/bin/celery -A footprono.worker.celery_app worker --pool=threads --concurrency=4 --loglevel=INFO
start beat .venv/bin/celery -A footprono.worker.celery_app beat --loglevel=INFO --schedule "$RUN/celerybeat-schedule"

sleep 3
curl -fsS "http://127.0.0.1:$PORT/api/v1/ready" && echo
