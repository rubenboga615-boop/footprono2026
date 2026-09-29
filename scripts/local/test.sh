#!/usr/bin/env bash
# Lint, typage et tests contre le PostgreSQL et le Redis locaux.
#   bash scripts/local/test.sh [options pytest]
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

start_postgres
start_redis
cd "$BACKEND"
export FP_TEST_DATABASE_URL="${FP_TEST_DATABASE_URL:-postgresql+asyncpg://$DB_USER:$DB_PASSWORD@127.0.0.1:$(pg_port)/${DB_NAME}_test}"
export FP_TEST_REDIS_URL="${FP_TEST_REDIS_URL:-redis://127.0.0.1:$REDIS_PORT/15}"

.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest "$@"
