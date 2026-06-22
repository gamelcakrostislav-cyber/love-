---
tags: [ops]
---
# Runbook

_Source: `README.md`, `.env.example`, `docker-compose.yml`, `scripts/`_

## Setup
```bash
cd control-plane
cp .env.example .env            # fill BOT_TOKEN, ADMIN_IDS, JWT_SECRET, CRYPTOPAY_API_TOKEN
docker compose up --build
curl localhost:8000/health      # {"status":"ok",...}
```
On startup the gateway runs `alembic upgrade head` and seeds
[[Plans and Pricing|plans]].

## Key env vars
| Var | Meaning |
|---|---|
| `JWT_SECRET` | signs [[Session Token]]s — `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `JWT_TTL_SECONDS` | token lifetime (900) |
| `ENTITLEMENT_CACHE_TTL` | [[Entitlement]] cache (60s) |
| `REQUEST_SIGNING_REQUIRED` | enforce signed protected calls ([[Nonce]]) |
| `DEVICE_REGISTER_COOLDOWN_HOURS` | new-[[Device Fingerprint\|device]] cooldown (24) |
| `IMPOSSIBLE_TRAVEL_MAX_KMH` | [[Impossible Travel]] threshold (1000) |
| `BOT_TOKEN` / `ADMIN_IDS` | Telegram bot + admins ([[Bot Commands]]) |
| `CRYPTOPAY_API_TOKEN` | Crypto Pay; unset → offline stub ([[Payments and Crypto Pay]]) |
| `REFERRAL_RATE_STANDARD` / `_BLOGGER` | 0.20 / 0.30 ([[Referral and Rev-Share]]) |

## Quick start (no payment)
1. `/start` then admin `/grant <your_id> monthly` → DMs you an [[API Key]].
2. `python scripts/client_example.py --api-key <KEY> --fingerprint my-laptop-001`.

## Tests
```bash
./scripts/run_tests.sh          # starts Postgres+Redis, installs deps, runs pytest
```
Covers key validation, device-limit, concurrency cap, webhook
signature/idempotency, expiry. See [[Roadmap]] phase 8.

> The bot must run somewhere with internet to Telegram (laptop/VPS), not an
> ephemeral cloud container.
