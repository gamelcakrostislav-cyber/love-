#!/usr/bin/env bash
# Open a temporary HTTPS tunnel to the local gateway so you can test the Telegram
# Mini App from your machine — no server, no domain, no Cloudflare account.
#
# What it does:
#   1. starts a Cloudflare "quick tunnel" to http://localhost:<PORT> (default 8000)
#   2. grabs the public https://<random>.trycloudflare.com URL
#   3. writes WEBAPP_URL=<url>/app into .env
#   4. recreates the bot container so it registers the "🚀 Open App" menu button
#   5. keeps the tunnel open (Ctrl-C to stop)
#
# Prereqs: the stack is already running (`docker compose up -d`) and `cloudflared`
# is installed (macOS: `brew install cloudflared`).
#
# Usage:  ./deploy/tunnel.sh [PORT]
set -euo pipefail

cd "$(dirname "$0")/.."             # -> control-plane/
PORT="${1:-8000}"
ENV_FILE=".env"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "❌ cloudflared not found. Install it:"
  echo "   macOS:  brew install cloudflared"
  echo "   other:  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ $ENV_FILE not found (run from the control-plane dir, and copy .env.example → .env)."
  exit 1
fi

if ! curl -fsS "http://localhost:${PORT}/health" >/dev/null 2>&1; then
  echo "❌ Gateway not reachable on http://localhost:${PORT}."
  echo "   Start the stack first:  docker compose up -d"
  exit 1
fi

LOG="$(mktemp)"
echo "🌩  Opening Cloudflare quick tunnel → http://localhost:${PORT} ..."
cloudflared tunnel --url "http://localhost:${PORT}" --no-autoupdate >"$LOG" 2>&1 &
TUNNEL_PID=$!
trap 'kill $TUNNEL_PID 2>/dev/null || true; rm -f "$LOG"' EXIT

URL=""
for _ in $(seq 1 30); do
  URL="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
  [ -n "$URL" ] && break
  sleep 1
done
if [ -z "$URL" ]; then
  echo "❌ Could not read the tunnel URL. cloudflared output:"; cat "$LOG"; exit 1
fi

WEBAPP_URL="${URL}/app"
if grep -q '^WEBAPP_URL=' "$ENV_FILE"; then
  sed -i.bak "s#^WEBAPP_URL=.*#WEBAPP_URL=${WEBAPP_URL}#" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
else
  printf '\nWEBAPP_URL=%s\n' "$WEBAPP_URL" >> "$ENV_FILE"
fi

echo "✅ Tunnel up:   $URL"
echo "✅ Mini App:    $WEBAPP_URL   (written to $ENV_FILE)"
echo "♻️  Recreating the bot so it registers the menu button ..."
docker compose up -d --force-recreate --no-deps bot >/dev/null 2>&1 || docker compose restart bot

cat <<EOF

🎉 Done. In Telegram, open your bot and tap the "🚀 Open App" menu button
   (bottom-left of the chat) — the Mini App loads over the tunnel.

   • Make sure BOT_TOKEN in $ENV_FILE is your real token (not CHANGE_ME),
     otherwise the Mini App API refuses requests by design.
   • This trycloudflare.com URL is temporary and changes each run.

Keep this terminal open. Press Ctrl-C to stop the tunnel.
EOF

wait $TUNNEL_PID
