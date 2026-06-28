# Control Plane & Licensing Layer

> 🆕 **New here / non-technical?** Start with **[QUICKSTART.md](QUICKSTART.md)** —
> simple step-by-step to run the bot on a Mac.

A Telegram-driven control plane for a SaaS arbitrage product. It handles
**commerce, licensing, and abuse prevention** around a product engine that does
not exist yet. The engine is represented by a single stubbed, license-protected
endpoint returning mock arbitrage opportunities.

> **Core design goal:** make it structurally hard to share API keys, run multiple
> accounts, or bypass a subscription. Entitlement is always decided server-side
> (zero trust). A leaked key alone is useless without passing device + session
> checks.

> 📓 **Obsidian vault:** a browsable, cross-linked version of this documentation
> lives in [`docs/vault/`](docs/vault/Home.md) — open that folder as an Obsidian
> vault for a graph view of the architecture and concepts.

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
6. **Payments** — `PaymentProvider` interface, Crypto Pay, signed + idempotent webhook, activation ✅
7. **Admin + worker** — admin commands, auto-expiry, session reaping ✅
8. **Tests** — pytest: key validation, device-limit, concurrency, webhook signature/idempotency, expiry ✅ ← _current_

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

A ready-to-run reference client does the session exchange **and** request signing
with no dependencies:

```bash
python scripts/client_example.py --api-key <YOUR_KEY> --fingerprint my-laptop-001
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

On first `/start` the user **picks a language** (English / Русский / Українська /
Español / Français) — it localizes the bot and sets the AI's reply language; a
**persistent button menu** (📋 Plans · 📊 Status · 🔑 Key · 📱 Devices · 🎁 Referrals ·
🆘 Human · 🌐 Language · ❓ Help) replaces typing commands. Change language anytime
with `/language` or the 🌐 button.

Client commands (aiogram 3.x long-polling):

| Command | Action |
|---|---|
| `/start [ref]` | provision account; `ref` = inviter's Telegram id captures a referral |
| `/plans` | list plans (inline buy buttons) |
| `/buy <plan> [code]` | create an invoice (Crypto Pay wired in Phase 6); optional discount code |
| `/promo <code>` | apply a discount code; the next purchase uses it (valid 30 min) |
| `/status` | subscription, expiry, API-key prefix |
| `/key` | show key prefix; reissue (confirm) — reissue disables the old key |
| `/devices` | list registered devices; remove one to free a slot |
| `/referrals` | invite link + stats (invited / pending / paid / earned), your rank, **Share** & **🏆 Leaderboard** buttons |
| `/leaderboard` | top referrers by earnings + your own rank (gamified growth loop) |
| `/mute` · `/unmute` | opt out of / back into promotional pushes (transactional DMs always send) |
| `/human` | hand off to a human (admins); free text otherwise goes to the AI agent |
| `/help` | command list |

Referral reward unlocks only when the referred user actually pays (handled at the
payment webhook in Phase 6); standard 20% / blogger 30%, one referrer per user,
no self-referral.

Admin commands (Telegram ids in `ADMIN_IDS`):

| Command | Action |
|---|---|
| `/stats` | active users, sessions, paid revenue, flagged + abuse counts |
| `/grant <telegram_id> <plan>` | grant/extend access (reuses webhook activation) |
| `/revoke <telegram_id>` | revoke subscription, disable keys, kill sessions |
| `/promonew <code> <20%\|$10> [plan=] [max=] [days=]` | create a discount code (forgiving syntax) |
| `/promoedit <code> …` | modify a code: amount, `plan=`, `max=`, `days=`, or `on`/`off` |
| `/promos` | list discount codes with usage |
| `/promooff <code>` | deactivate a discount code |
| `/flags` | review flagged keys + recent abuse events |
| `/unflag <key_prefix\|id>` | clear a flag |
| `/reply <telegram_id> <message>` | answer a user in a human handoff |
| `/close <telegram_id>` | end a human handoff (user returns to the AI agent) |

## AI support agent

The bot answers free-text questions with an AI support agent. Customers just type
a question; the agent replies, grounded in the product docs + the user's own
subscription status (short Redis-backed memory). It only *answers* — it never
grants access.

- Any **OpenAI-compatible** provider works via the `SUPPORT_*` env vars. Default
  is **free Groq** — get a no-credit-card key at
  [console.groq.com/keys](https://console.groq.com/keys) and set `SUPPORT_API_KEY`.
  Leave it as `CHANGE_ME` to disable (the bot still runs with a fallback reply).
  Swap provider by changing `SUPPORT_BASE_URL` / `SUPPORT_MODEL` (OpenAI, OpenRouter…).
- **Human handoff:** if a user asks for a person (or sends `/human`, or the agent
  can't help), the user is put into handoff mode, the admins are pinged, and the
  user's messages are relayed to admins. Admins answer through the bot with
  `/reply <telegram_id> <message>` and end the chat with `/close <telegram_id>`.

## Worker

The `worker` service (APScheduler) runs an expiry sweep every minute:
subscriptions past `expires_at` → `expired`, their keys disabled, their Redis
sessions killed, stale session rows reaped. Expiry is therefore enforced
server-side — the client can never self-extend, and revocation/expiry propagates
within the entitlement cache window.

It also sends **expiry reminders**: every `EXPIRY_REMINDER_MINUTES` it DMs users
whose subscription falls into a days-left band (`EXPIRY_REMINDER_DAYS=3,1`),
localized, with a one-tap renew button — deduped per band via a Redis marker so
nobody is spammed.

**Client push & automation** (all respect each user's `/mute` opt-out):
- **Onboarding drip** — nudges not-yet-subscribed users at `ONBOARDING_DRIP_DAYS`
  (default `1,3`) since signup.
- **Win-back** — DMs lapsed users `WINBACK_DAYS` after they expire.
- **Weekly digest** — a summary DM to active subscribers (plan, days left, referral
  earnings), once per 7 days.
- **Admin** — `/push <all|active|trial|inactive> <msg>` targets a segment;
  `/broadcast` reaches everyone (transactional). Admins also get auto **abuse
  alerts**. (Plus the Notion reconcile job when enabled.)

## Notion sync (advanced database / CRM)

Optionally mirror your whole business into a **Notion workspace** as eight linked
databases — **Customers, Payments, Subscriptions, Referrals, Commissions, Flags &
Abuse, Overview (daily KPIs), Audit Log** — so you get a rich, filterable
dashboard without touching SQL.

- **Auto-provisioned:** on first run the worker creates the databases (with emoji
  icons) under a parent page you share with the integration, and remembers their
  ids (in the `notion_sync` table). No manual table-building. A stored schema
  version lets later builds add new properties/databases to an existing workspace.
- **Linked, not flat:** child rows carry a Notion *relation* back to their
  Customer, so you get real roll-ups and views. Customer rows are icon-tagged
  💎 paid · 🧪 trial · ⚪ none.
- **KPI dashboard:** the **Overview** database keeps one row per day (revenue,
  active/paid/trial, signups, flags…) — chart it in Notion for a live dashboard.
- **One-way mirror + best-effort:** a worker job reconciles every
  `NOTION_RECONCILE_MINUTES` (default 3); a new sale is pushed within seconds of
  the paid webhook. Unchanged rows are skipped via a content hash; a Redis lock
  prevents overlapping runs; a per-run write budget keeps us under Notion's
  ~3 req/s; every call is guarded so a Notion outage never affects the bot.
- **Two-way actions (opt-out):** set a Customer's **Action** field
  (grant/revoke/blogger) and the bot applies it via the *same* server-side path
  as admin commands — never bypassing entitlement, with reset-first so it can't
  double-apply. Disable with `NOTION_ALLOW_ACTIONS=false`.
- **Off by default:** set `NOTION_SYNC_ENABLED=true`, `NOTION_API_KEY` and
  `NOTION_PARENT_PAGE_ID` to enable. Admins check status / force a sync with
  `/notion` and `/notion sync`. Step-by-step setup: [`deploy/notion.md`](deploy/notion.md).

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

## Tests

```bash
cd control-plane
./scripts/run_tests.sh          # starts postgres+redis, installs deps, runs pytest
```

The suite needs a Postgres + Redis (the compose services) because the licensing
logic is inseparable from both. It covers:

| File | Covers |
|---|---|
| `test_keys.py` | key gen/hash, validate active/unknown/disabled, reissue disables old |
| `test_device_limit.py` | first device active, 2nd → cooldown + abuse_event, auto-approve after window |
| `test_concurrency.py` | over-cap eviction (oldest killed + logged), within-cap keeps both |
| `test_webhook.py` | Crypto Pay signature verify, paid-event parse, activation idempotency |
| `test_expiry.py` | expiry → sub expired, key disabled, Redis session killed |

CI/web sessions: `scripts/session_setup.sh` (wired as a SessionStart hook) installs
deps and brings up Postgres + Redis best-effort.

## Security notes

- Secrets only via `.env` (git-ignored); never committed.
- API keys stored as `sha256(key)` + 8-char prefix — raw key shown once.
- Payment webhooks verify the provider signature before activating anything.
- Webhooks are idempotent by external invoice id.
