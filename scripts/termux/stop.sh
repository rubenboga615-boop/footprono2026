#!/data/data/com.termux/files/usr/bin/bash
# Arrête l'API, le worker et le beat (PostgreSQL et Redis restent actifs,
# utiliser --all pour les arrêter aussi).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="${FP_RUN_DIR:-$ROOT/.run}"
PGDATA="${FP_PGDATA:-$PREFIX/var/lib/postgresql}"

for name in beat worker api; do
    pidfile="$RUN/$name.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        kill "$(cat "$pidfile")" && echo "$name arrêté"
    fi
    rm -f "$pidfile"
done

if [ "${1:-}" = "--all" ]; then
    redis-cli shutdown nosave 2>/dev/null && echo "redis arrêté" || true
    pg_ctl -D "$PGDATA" stop 2>/dev/null && echo "postgresql arrêté" || true
    command -v termux-wake-unlock >/dev/null && termux-wake-unlock
fi
