#!/usr/bin/env bash
# Gateway entrypoint: apply migrations, seed the plan catalog, then serve.
set -euo pipefail

echo "[start] applying migrations…"
alembic upgrade head

echo "[start] seeding plans…"
python -m scripts.seed_plans

echo "[start] launching gateway…"
exec uvicorn app.gateway.main:app --host 0.0.0.0 --port 8000
