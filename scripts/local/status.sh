#!/usr/bin/env bash
# État des services FootProno.
set -uo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

if pg_online; then echo "postgresql : actif (port $(pg_port))"; else echo "postgresql : arrêté"; fi
if redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then echo "redis      : actif"; else echo "redis      : arrêté"; fi
for name in api worker beat; do
    pidfile="$RUN/$name.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "$(printf '%-10s' "$name") : actif (pid $(cat "$pidfile"))"
    else
        echo "$(printf '%-10s' "$name") : arrêté"
    fi
done
curl -fsS "http://127.0.0.1:$PORT/api/v1/ready" 2>/dev/null && echo || echo "api        : /ready injoignable"
