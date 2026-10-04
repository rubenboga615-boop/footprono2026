#!/usr/bin/env bash
# État des services FootProba.
set -uo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

if pg_running; then echo "postgresql : actif (port $PG_PORT)"; else echo "postgresql : arrêté"; fi
if redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then echo "redis      : actif"; else echo "redis      : arrêté"; fi
for name in api worker beat; do
    pidfile="$RUN/$name.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        printf '%-10s : actif (pid %s)\n' "$name" "$(cat "$pidfile")"
    else
        printf '%-10s : arrêté\n' "$name"
    fi
done
curl -fsS "http://127.0.0.1:$PORT/api/v1/ready" 2>/dev/null && echo || echo "api        : /ready injoignable"
