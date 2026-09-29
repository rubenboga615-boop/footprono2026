#!/data/data/com.termux/files/usr/bin/bash
# Lance lint, typage et tests contre le PostgreSQL et le Redis locaux.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
DB_USER="${FP_DB_USER:-footprono}"
DB_PASSWORD="${FP_DB_PASSWORD:-footprono}"
export FP_TEST_DATABASE_URL="${FP_TEST_DATABASE_URL:-postgresql+asyncpg://$DB_USER:$DB_PASSWORD@127.0.0.1:5432/footprono_test}"
export FP_TEST_REDIS_URL="${FP_TEST_REDIS_URL:-redis://127.0.0.1:6379/15}"

.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest "$@"
