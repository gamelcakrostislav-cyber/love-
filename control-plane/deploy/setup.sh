#!/usr/bin/env bash
# One-shot setup for a fresh Ubuntu 22.04/24.04 VPS.
# Installs Docker, clones the repo, and prepares .env. Run as root (or with sudo):
#
#   curl -fsSL https://raw.githubusercontent.com/gamelcakrostislav-cyber/love-/main/control-plane/deploy/setup.sh | bash
#
# ...or copy this file to the server and run:  bash setup.sh
set -euo pipefail

REPO_URL="https://github.com/gamelcakrostislav-cyber/love-.git"
CLONE_DIR="${CLONE_DIR:-/opt/lovebot}"

echo "==> Updating packages"
apt-get update -y
apt-get install -y ca-certificates curl git

echo "==> Installing Docker (official convenience script)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "==> Cloning repo into ${CLONE_DIR}"
if [ -d "${CLONE_DIR}/.git" ]; then
  git -C "${CLONE_DIR}" pull --ff-only
else
  git clone "${REPO_URL}" "${CLONE_DIR}"
fi

cd "${CLONE_DIR}/control-plane"

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "==> Created .env from .env.example."
  echo "    EDIT IT NOW before starting:  nano ${CLONE_DIR}/control-plane/.env"
  echo "    Required: BOT_TOKEN, ADMIN_IDS, JWT_SECRET, DOMAIN,"
  echo "              CRYPTOPAY_API_TOKEN, SUPPORT_API_KEY (Groq)."
else
  echo "==> .env already exists — leaving it untouched."
fi

echo
echo "==> Done. To launch in production (with HTTPS):"
echo "    cd ${CLONE_DIR}/control-plane"
echo "    docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build"
