#!/usr/bin/env bash
# Lint, typage et tests contre le PostgreSQL et le Redis locaux.
#   bash scripts/termux/test.sh [options pytest]
set -euo pipefail
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"

[ -x "$VENV/bin/pytest" ] || die "outils de test absents : lancer bash scripts/termux/setup.sh --dev"
command -v ruff >/dev/null 2>&1 || die "ruff absent : lancer bash scripts/termux/setup.sh --dev"
start_postgres
start_redis
cd "$BACKEND"
export FP_TEST_DATABASE_URL="${FP_TEST_DATABASE_URL:-postgresql+asyncpg://$DB_USER:$DB_PASSWORD@127.0.0.1:$PG_PORT/${DB_NAME}_test}"
export FP_TEST_REDIS_URL="${FP_TEST_REDIS_URL:-redis://127.0.0.1:$REDIS_PORT/15}"

ruff check .
ruff format --check .
"$VENV/bin/mypy"
"$VENV/bin/pytest" "$@"
