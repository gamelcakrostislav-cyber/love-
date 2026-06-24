---
tags: [ops, integration]
---
# Notion Sync

_Source: `app/integrations/notion.py`, `app/services/notion_sync.py`,
`app/worker/scheduler.py`, `app/bot/handlers/admin.py`_

Optional, one-way mirror of business data into a **Notion** workspace as six
**linked** databases — a no-SQL "advanced database" / CRM dashboard for the
owner. Off by default; never affects entitlement (which stays server-side,
[[Zero-Trust Principles]]).

## Databases (auto-provisioned)
Created under a parent page on first run, in dependency order so relations
resolve. Each gets an emoji icon; a stored schema version (`_SCHEMA_VERSION` on
the db mapping row) lets later builds PATCH new props/icons onto existing DBs.

| Database | Source ([[Data Model]]) | Relations |
|----------|-------------------------|-----------|
| 👥 Customers | `User` (+ derived plan, key prefix, devices, referrals, earnings) | — |
| 💸 Payments | `Payment` | → Customers |
| 🔄 Subscriptions | `Subscription` | → Customers |
| 🤝 Referrals | `Referral` | → Referrer, Referred |
| 💰 Commissions | `Commission` | → Referrer, Payment |
| 🚩 Flags & Abuse | `AbuseEvent` | → Customers |
| 📈 Overview | daily KPI snapshot (revenue, active/paid/trial, signups, flags) | — |
| 📜 Audit Log | `AuditLog` | — |

Customer pages are icon-tagged by state: 💎 paid · 🧪 trial · ⚪ none.

## How it works
- **Mapping table:** `notion_sync(kind, ref) → notion_id, content_hash`. `kind="database"`
  stores the six database ids; entity rows store their page id + the hash of the
  last pushed payload.
- **Reconcile job:** the [[Worker and Expiry|worker]] runs `notion_sync.reconcile`
  every `NOTION_RECONCILE_MINUTES` (default 3). It ensures the databases exist,
  then upserts Customers first (building a `user_id → page_id` map for relations),
  then the child entities.
- **Idempotent & cheap:** a row whose `content_hash` is unchanged is skipped (no
  API call). New/changed rows are created/patched.
- **Guards:** a Redis [[Nonce|lock]] (`lock:sync:notion`) prevents overlapping
  runs; a per-run write budget (60) bounds traffic under Notion's ~3 req/s; every
  network call is wrapped so a Notion outage never breaks the bot or worker.

## Config
`NOTION_SYNC_ENABLED`, `NOTION_API_KEY`, `NOTION_PARENT_PAGE_ID`,
`NOTION_API_BASE`, `NOTION_VERSION`, `NOTION_RECONCILE_MINUTES`. Disabled while
`NOTION_API_KEY=CHANGE_ME` or no parent page. Setup: `deploy/notion.md`.

## Instant push
On a paid webhook (and admin `/grant`), `push_user(db, user_id)` mirrors that one
customer + their latest payment immediately (best-effort, short lock), so new
sales appear in seconds instead of waiting for the periodic pass.

## Two-way actions (opt-out: `NOTION_ALLOW_ACTIONS`)
The Customers DB has an **Action** select (`grant_*`/`revoke`/`*_blogger`).
`apply_actions` (run before reconcile each tick) queries rows with Action set,
maps the page back to a user via the `notion_sync` table, then **reset-first**
clears the field and runs the action through the *same* [[Licensing Model|server-side]]
[[Bot Commands|/grant]]/[[Bot Commands|/revoke]] services (actor `notion`,
audited). Reset-before-apply guarantees no double-grant on retry. It never
bypasses [[Zero-Trust Principles|zero-trust]] — a grant issues a real subscription.

## Admin ([[Bot Commands]])
- `/notion` — status + links to each database (+ whether actions are on).
- `/notion sync` — force a reconcile now.

## Notes
- The mirror is one-way for *display* fields; only the Action field flows back,
  and only through the secure grant/revoke path. Full [[API Key|keys]] are never
  synced — only the public prefix.
