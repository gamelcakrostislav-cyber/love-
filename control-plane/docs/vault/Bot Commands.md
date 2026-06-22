---
tags: [bot]
---
# Bot Commands

_Source: `app/bot/handlers/{client,admin}.py`_

aiogram 3.x long-polling bot. It only displays server-side state and triggers
server-side actions — it never grants [[Entitlement|entitlement]] itself.

## Client commands

| Command | Action |
|---|---|
| `/start [ref]` | provision account; `ref` = inviter's Telegram id captures a [[Referral and Rev-Share\|referral]] |
| `/plans` | list [[Plans and Pricing\|plans]] (inline buy buttons) |
| `/buy <plan>` | create an invoice → [[Payments and Crypto Pay]] |
| `/status` | subscription, expiry, [[API Key]] prefix |
| `/key` | show key prefix; reissue (confirm) — reissue disables the old key |
| `/devices` | list registered [[Device Fingerprint\|devices]]; remove one to free a slot |
| `/help` | command list |

## Admin commands
Gated by an `IsAdmin` filter on `ADMIN_IDS`.

| Command | Action |
|---|---|
| `/stats` | active users, sessions, paid revenue, flagged + abuse counts |
| `/grant <telegram_id> <plan>` | grant/extend access (reuses webhook activation) |
| `/revoke <telegram_id>` | revoke subscription, disable keys, kill sessions ([[Worker and Expiry]]) |
| `/flags` | review flagged keys + recent abuse events ([[Anti-Abuse]]) |
| `/unflag <key_prefix\|id>` | clear a flag |

The bot DMs a freshly issued key once (via a transient Bot in the gateway, for
webhook activation). See [[Runbook]] to configure `BOT_TOKEN` / `ADMIN_IDS`.
