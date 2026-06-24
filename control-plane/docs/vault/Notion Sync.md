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
resolve:

| Database | Source ([[Data Model]]) | Relations |
|----------|-------------------------|-----------|
| Customers | `User` (+ derived plan, key prefix, devices, referrals, earnings) | — |
| Payments | `Payment` | → Customers |
| Subscriptions | `Subscription` | → Customers |
| Referrals | `Referral` | → Referrer, Referred |
| Commissions | `Commission` | → Referrer, Payment |
| Flags & Abuse | `AbuseEvent` | → Customers |

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

## Admin ([[Bot Commands]])
- `/notion` — status + links to each database.
- `/notion sync` — force a reconcile now.

## Notes
- One-way: editing Notion does not change the product; the next sync overwrites
  synced fields. Full [[API Key|keys]] are never synced — only the public prefix.
