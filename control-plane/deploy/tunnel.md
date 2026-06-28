# Test the Mini App from your Mac (Cloudflare quick tunnel)

The Telegram Mini App needs a public **HTTPS** URL to load. Before you commit to
real hosting, you can expose your local stack through a temporary Cloudflare
tunnel — no domain, no account, no card.

## One-time install

```bash
brew install cloudflared      # macOS
```

## Run it

```bash
cd control-plane
docker compose up -d          # 1. start gateway + bot + worker
./deploy/tunnel.sh            # 2. open the tunnel (keep this terminal open)
```

`tunnel.sh` will:
1. open `https://<random>.trycloudflare.com` → your local gateway (port 8000),
2. write `WEBAPP_URL=<that-url>/app` into `.env`,
3. recreate the **bot** container so it registers the **🚀 Open App** menu button.

Then in Telegram, open your bot and tap **🚀 Open App** (bottom-left of the chat).
The dashboard loads — Home, Plans, Devices, Referrals.

## Important

- **`BOT_TOKEN` must be your real token** (not `CHANGE_ME`). The Mini App API
  verifies Telegram's `initData` with it and *refuses every request* while the
  token is the placeholder — that's the intended fail-closed behavior.
- Optionally set `BOT_USERNAME=yourbot` in `.env` so referral invite links render
  without an extra API call.
- The `trycloudflare.com` URL is **temporary** and changes on each run. Re-running
  the script updates `.env` and the menu button automatically.
- Stop the tunnel with **Ctrl-C**. To remove the menu button afterwards, blank
  `WEBAPP_URL=` in `.env` and `docker compose up -d --force-recreate --no-deps bot`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Gateway not reachable" | `docker compose up -d` first; check `docker compose ps` |
| Mini App shows "Open this from inside Telegram" | You opened the URL in a browser — it only works launched from the bot |
| API returns 401 | `BOT_TOKEN` is still `CHANGE_ME` — set the real one and re-run the script |
| Menu button missing | Re-run the script; or `docker compose logs bot | grep -i menu` |

When you're ready for permanent hosting (so card payments + the Mini App stay up
24/7), see [`deploy/README.md`](README.md) for the VPS + Caddy (auto-HTTPS) setup.
