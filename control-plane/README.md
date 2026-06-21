# Control Plane & Licensing Layer

A Telegram-driven control plane for a SaaS arbitrage product. It handles
**commerce, licensing, and abuse prevention** around a product engine that does
not exist yet. The engine is represented by a single stubbed, license-protected
endpoint returning mock arbitrage opportunities.

> **Core design goal:** make it structurally hard to share API keys, run multiple
> accounts, or bypass a subscription. Entitlement is always decided server-side
> (zero trust). A leaked key alone is useless without passing device + session
> checks.

## Architecture

Three processes share one codebase (`app/core`, `app/models`, `app/services`)
so licensing logic lives in exactly one place:

| Service    | Role                                                            |
|------------|----------------------------------------------------------------|
| `gateway`  | FastAPI: `/auth/session` token exchange, protected endpoint, payment webhook |
| `bot`      | aiogram 3.x: client commerce + admin commands                  |
| `worker`   | APScheduler: subscription expiry + Redis session reaping       |
| `postgres` | system of record                                               |
| `redis`    | live sessions, rate-limit buckets, IP velocity, entitlement cache |

### Licensing flow (the backbone)

```
API key (long-lived, issued once after payment)
   │  POST /auth/session  { api_key, device_fingerprint, context }
   ▼
License service  ── validates key + subscription
                 ── enforces device & concurrency limits
                 ── runs risk checks (IP velocity / impossible travel)
                 ▼
Short-lived JWT (15 min), bound to device fingerprint + session id
   │  Protected endpoints accept ONLY this token, never the raw key.
   ▼
Protected endpoint ── verifies JWT signature + session still live in Redis
```

The raw key never touches the protected endpoints — one chokepoint where all
sharing/abuse is detected, and a stolen key cannot be used without device +
session checks.

## Plans

| Plan      | Price | Duration | Entitlement                         |
|-----------|-------|----------|-------------------------------------|
| `trial`   | free  | 7 days   | only ≤2% profitability opportunities |
| `monthly` | $49   | 30 days  | all opportunities                   |
| `yearly`  | $479  | 365 days | all opportunities                   |

**Referral / rev-share:** standard referrer 20%, blogger 30%. Reward unlocks
only after the referred account actually pays, and is capped per identity
cluster to stop self-referral farming.

## Local setup (docker-compose)

```bash
cd control-plane
cp .env.example .env          # then fill in BOT_TOKEN, CRYPTOPAY_API_TOKEN, JWT_SECRET, ADMIN_IDS
docker compose up --build
```

Check health once the stack is up:

```bash
curl localhost:8000/health
# {"status":"ok","checks":{"postgres":true,"redis":true}}
```

Generate a strong JWT secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Build phases

1. **Scaffold** — structure, `.env.example`, docker-compose, Postgres+Redis, health-check ← _current_
2. DB models + Alembic migration + plan seeder
3. Licensing core (key issue/validate, `/auth/session`, device binding, concurrency, rate-limit, stubbed protected endpoint)
4. Anti-abuse layer (fingerprint dedup, IP velocity, abuse_events, flagging, audit log)
5. Bot (client commands incl. `/devices` and key reissue)
6. Payments (provider interface, Crypto Pay, signed + idempotent webhook, activation)
7. Admin + worker (admin commands, auto-expiry, session reaping)
8. Tests (pytest)

## Security notes

- Secrets only via `.env` (git-ignored); never committed.
- API keys stored as `sha256(key)` + 8-char prefix — raw key shown once.
- Payment webhooks verify the provider signature before activating anything.
- Webhooks are idempotent by external invoice id.
