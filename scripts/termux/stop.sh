#!/usr/bin/env bash
# Arrête l'API, le worker et le beat. Avec --all, arrête aussi Redis et PostgreSQL.
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

for name in beat worker api; do
    pidfile="$RUN/$name.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        pid="$(cat "$pidfile")"
        kill "$pid"
        for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
        echo "$name arrêté"
    fi
    rm -f "$pidfile"
done

if [ "${1:-}" = "--all" ]; then
    redis-cli -p "$REDIS_PORT" shutdown nosave >/dev/null 2>&1 && echo "redis arrêté" || true
    if pg_running; then
        pg_ctl -D "$PGDATA" -m fast stop >/dev/null && echo "postgresql arrêté"
    fi
    command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock
fi
