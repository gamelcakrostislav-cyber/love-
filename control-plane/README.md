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

On startup the gateway automatically applies migrations (`alembic upgrade head`)
and seeds the plan catalog. Check health once the stack is up:

```bash
curl localhost:8000/health
# {"status":"ok","checks":{"postgres":true,"redis":true}}
```

### Database (manual)

```bash
alembic upgrade head          # apply schema
python -m scripts.seed_plans  # seed/refresh the trial / monthly / yearly plans
alembic downgrade -1          # roll back
```

Tables: `users`, `plans`, `subscriptions`, `api_keys`, `devices`, `sessions`,
`payments`, `referrals`, `commissions`, `abuse_events`, `audit_log`.

Generate a strong JWT secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Build phases

1. **Scaffold** — structure, `.env.example`, docker-compose, Postgres+Redis, health-check ✅
2. **DB** — models + Alembic migration + plan seeder ✅
   _(extends the spec schema with `referrals` + `commissions` tables and `is_blogger`/`referred_by` on users for the rev-share system)_
3. **Licensing core** — key issue/validate, `/auth/session`, device binding, concurrency, rate-limit, stubbed protected endpoint ✅
4. **Anti-abuse layer** — fingerprint dedup, IP velocity / impossible travel, signed anti-replay, abuse_events, flagging, audit log ✅
5. **Bot** — client commands incl. `/devices` and key reissue; referral capture on `/start <ref>` ✅
6. **Payments** — `PaymentProvider` interface, Crypto Pay, signed + idempotent webhook, activation ✅ ← _current_
7. Admin + worker (admin commands, auto-expiry, session reaping)
8. Tests (pytest)

## API (licensing core)

Exchange a key for a short-lived, device-bound token, then call the protected
engine with that token only:

```bash
# 1. Session token (raw key used here and nowhere else)
curl -s localhost:8000/auth/session -H 'content-type: application/json' -d '{
  "api_key": "<RAW_KEY>",
  "device_fingerprint": "device-abc-123"
}'
# -> { "token": "...", "session_id": "...", "expires_at": "...", "plan": "monthly", ... }

# 2. Protected engine — token + bound fingerprint + signed (timestamp/nonce/HMAC)
curl -s localhost:8000/v1/opportunities \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'X-Device-Fingerprint: device-abc-123' \
  -H 'X-Timestamp: <UNIX_TS>' -H 'X-Nonce: <RANDOM>' -H 'X-Signature: <HMAC>'
# trial keys see only opportunities with profitability <= 2%; paid keys see all
```

Protected requests are HMAC-signed with the per-session `signing_secret`
returned by `/auth/session` (delivered once, never re-sent):

```
X-Signature = HMAC_SHA256(signing_secret,
    "<timestamp>\n<nonce>\n<METHOD>\n<path>\n<sha256(body)>")
```

The nonce is single-use and the timestamp must be within
`REQUEST_SIGNATURE_MAX_SKEW` seconds, so a sniffed request can't be replayed and
a sniffed token alone can't forge new ones. (Set `REQUEST_SIGNING_REQUIRED=false`
to disable during early integration.)

Enforcement at `/auth/session` (all server-side): key validity → active
subscription → device limit (24h cooldown beyond `max_devices`) → **multi-account
fingerprint dedup** → concurrency cap (evict oldest + log) → **IP velocity /
impossible-travel** → issue device-bound JWT mirrored in Redis.

### Anti-abuse summary

| Vector | Defense |
|---|---|
| Key sharing | device binding + 24h cooldown, concurrency cap (evict+log), per-key rate limit, signed anti-replay |
| Multi-accounting | fingerprint dedup across accounts → flag cluster; payer-fingerprint linkage at payment |
| Impossible travel | geo velocity between consecutive sessions → flag above threshold |
| Subscription bypass | server-side entitlement recompute every session; flagged (not banned) state surfaced to admin |

Flags set `api_keys.flagged`, record an `abuse_event`, and bump `risk_score` — the
key keeps working until an admin acts (low false-positive cost).

## Telegram bot

Client commands (aiogram 3.x long-polling):

| Command | Action |
|---|---|
| `/start [ref]` | provision account; `ref` = inviter's Telegram id captures a referral |
| `/plans` | list plans (inline buy buttons) |
| `/buy <plan>` | create an invoice (Crypto Pay wired in Phase 6) |
| `/status` | subscription, expiry, API-key prefix |
| `/key` | show key prefix; reissue (confirm) — reissue disables the old key |
| `/devices` | list registered devices; remove one to free a slot |
| `/help` | command list |

Referral reward unlocks only when the referred user actually pays (handled at the
payment webhook in Phase 6); standard 20% / blogger 30%, one referrer per user,
no self-referral.

## Payments

`PaymentProvider` abstraction with a **Crypto Pay** (`@CryptoBot`) implementation
(`app/payments/`); falls back to an offline stub when `CRYPTOPAY_API_TOKEN` is
unset so `/buy` works in local dev.

Webhook: `POST /webhooks/cryptopay`
1. **Verify signature first** — `HMAC_SHA256(body, key=SHA256(api_token))` against
   the `crypto-pay-api-signature` header. A forged/unsigned call grants nothing.
2. **Idempotent** — deduped by `external_id`; a replayed "paid" never extends a
   subscription twice or double-credits a referral.
3. **Activate** — mark paid → create/extend subscription (`+duration_days`) →
   issue key (once, DM'd) or reactivate → record `payer_fingerprint` (+ multi-account
   linkage) → unlock referral commission → invalidate entitlement cache.

Point Crypto Pay's webhook at `https://<host>/webhooks/cryptopay`.

## Security notes

- Secrets only via `.env` (git-ignored); never committed.
- API keys stored as `sha256(key)` + 8-char prefix — raw key shown once.
- Payment webhooks verify the provider signature before activating anything.
- Webhooks are idempotent by external invoice id.
