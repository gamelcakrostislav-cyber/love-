#!/usr/bin/env bash
# Run the test suite against the compose Postgres + Redis.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[tests] starting postgres + redis…"
docker compose up -d postgres redis

echo "[tests] waiting for postgres…"
for _ in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-control}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

export DATABASE_URL="postgresql+asyncpg://control:control@localhost:5432/control_plane_test"
export REDIS_URL="redis://localhost:6379/15"
export JWT_SECRET="test-secret"
export REQUEST_SIGNING_REQUIRED="false"
export CRYPTOPAY_API_TOKEN="test-token"

echo "[tests] installing deps…"
pip install -q -e ".[dev]"

echo "[tests] running pytest…"
pytest -q "$@"
