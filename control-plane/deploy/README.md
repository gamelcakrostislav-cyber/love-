# Deploy: 24/7 VPS hosting + real Crypto Pay payments

This guide takes the bot from "runs on my Mac" to "always online, accepts real
crypto payments." Total time: ~20 minutes. Cost: ~$4–6/month for the server.

You'll do four things:

1. Rent a small Linux server (VPS)
2. Point a domain at it (needed for HTTPS, which Crypto Pay requires)
3. Run the setup script + fill in `.env`
4. Launch in production mode (HTTPS is automatic)

---

## 1. Rent a VPS

Any of these work. Pick the cheapest small plan (1 vCPU / 2 GB RAM is plenty):

- **Hetzner Cloud** (CX22, ~€4/mo) — best value
- **DigitalOcean** ($6/mo droplet) — simplest UI
- **Contabo / Vultr / Linode** — also fine

Choose **Ubuntu 24.04** as the image. After it's created you'll get an **IP
address** (e.g. `203.0.113.10`) and a root password or SSH key.

Connect from your Mac's Terminal:

```bash
ssh root@203.0.113.10
```

## 2. Point a domain at the server

Crypto Pay sends payment confirmations to a webhook, which needs **HTTPS** —
and HTTPS needs a domain name.

- Buy a cheap domain (Namecheap, Cloudflare, Porkbun — ~$1–10/yr), **or** use a
  free subdomain (e.g. [DuckDNS](https://www.duckdns.org)).
- Create an **A record** pointing your domain (e.g. `bot.example.com`) at the
  server's IP. Wait a few minutes for it to propagate.

You can verify with: `ping bot.example.com` (should show the server's IP).

## 3. Run setup + configure `.env`

On the server:

```bash
curl -fsSL https://raw.githubusercontent.com/gamelcakrostislav-cyber/love-/main/control-plane/deploy/setup.sh | bash
```

This installs Docker, clones the repo to `/opt/lovebot`, and creates a `.env`.
Now edit it:

```bash
nano /opt/lovebot/control-plane/.env
```

Fill in:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | from @BotFather |
| `ADMIN_IDS` | your Telegram numeric id (e.g. `1966832731`) |
| `JWT_SECRET` | any long random string |
| `DOMAIN` | the domain from step 2 (e.g. `bot.example.com`) |
| `CRYPTOPAY_API_TOKEN` | from @CryptoBot → Crypto Pay → Create App (see step 5) |
| `SUPPORT_API_KEY` | your free Groq key (see "Turn on the AI" below) |

Save in nano: `Ctrl+O`, `Enter`, then `Ctrl+X`.

## 4. Launch (production, with HTTPS)

```bash
cd /opt/lovebot/control-plane
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
```

Caddy automatically fetches a TLS certificate for your domain. Check it's up:

```bash
curl https://bot.example.com/health      # -> {"status":"ok"}
docker compose ps                          # all services "running"
```

Everything is set to `restart: unless-stopped`, so the bot survives reboots and
crashes. To update later: `git pull && docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build`.

---

## 5. Real Crypto Pay payments

1. In Telegram open **@CryptoBot** → **Crypto Pay** → **Create App**. Copy the
   **API Token** into `CRYPTOPAY_API_TOKEN` in `.env`.
2. In the same Crypto Pay app settings, set the **Webhook URL** to:

   ```
   https://bot.example.com/webhooks/cryptopay
   ```

3. Restart so the new token loads:

   ```bash
   docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
   ```

Now `/buy monthly` in the bot creates a real invoice; once the user pays, Crypto
Pay calls your webhook and the subscription activates automatically. The webhook
signature is verified server-side (`CRYPTOPAY_WEBHOOK_ENABLED=true`), so only
genuine Crypto Pay calls are honored.

---

## Turn on the AI (free, no credit card)

1. Go to <https://console.groq.com/keys>, sign in, **Create API Key**, copy it.
2. Put it in `.env`: `SUPPORT_API_KEY=gsk_...`
3. Restart: `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d`

The bot now answers free-text product/support questions in the user's chosen
language, and hands off to you (`/human`) when asked. Leave the key as
`CHANGE_ME` to keep the AI off — the buttons and commands still work.

---

## Troubleshooting

- **HTTPS cert won't issue** → DNS A record isn't pointing at the server yet, or
  ports 80/443 are blocked by the provider's firewall. Open them.
- **`curl https://.../health` fails** → check `docker compose logs caddy` and
  `docker compose logs gateway`.
- **Bot doesn't respond** → `docker compose logs bot`; confirm `BOT_TOKEN` is set.
- **Payments don't activate** → confirm the Crypto Pay webhook URL exactly matches
  `https://<DOMAIN>/webhooks/cryptopay` and the token in `.env` is the same app's.
