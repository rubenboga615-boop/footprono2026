#!/usr/bin/env bash
# Démarre la pile complète : PostgreSQL, Redis, API, worker, beat.
#   bash scripts/local/start.sh
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

mkdir -p "$RUN"
start_postgres
start_redis
load_env
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
# Pool de threads : fonctionne partout, y compris sous proot où les sémaphores
# POSIX du pool « prefork » ne sont pas garantis. Surcharger avec FP_CELERY_POOL.
start worker .venv/bin/celery -A footprono.worker.celery_app worker \
    --pool="${FP_CELERY_POOL:-threads}" --concurrency="${FP_CELERY_CONCURRENCY:-4}" --loglevel=INFO
start beat .venv/bin/celery -A footprono.worker.celery_app beat \
    --loglevel=INFO --schedule "$RUN/celerybeat-schedule"

for _ in $(seq 1 15); do
    if curl -fsS "http://127.0.0.1:$PORT/api/v1/ready" 2>/dev/null; then
        echo
        exit 0
    fi
    sleep 1
done
die "l'API ne répond pas prête sur le port $PORT (voir $RUN/api.log)"
