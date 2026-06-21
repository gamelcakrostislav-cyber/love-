#!/usr/bin/env bash
# Best-effort SessionStart setup so web sessions can run the suite:
# install deps if missing and bring up Postgres + Redis. Never fails the session.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 0

python -c "import pytest" 2>/dev/null || pip install -q -e ".[dev]" 2>/dev/null || true

if command -v docker >/dev/null 2>&1; then
  docker compose up -d postgres redis 2>/dev/null || true
fi

exit 0
