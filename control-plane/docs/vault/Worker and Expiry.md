---
tags: [ops]
---
# Worker and Expiry

_Source: `app/worker/scheduler.py`, `app/services/revocation.py`_

The `worker` service (APScheduler `AsyncIOScheduler`) runs an **expiry sweep
every minute** (and once on boot). This is what makes expiry server-enforced —
the client can never self-extend ([[Zero-Trust Principles]]).

## Sweep (`tick`)
- `expire_due()` — subscriptions past `expires_at` → `expired`; their
  [[API Key|keys]] disabled; their Redis [[Session Token|sessions]] killed.
- `reap_sessions()` — stale DB session rows marked revoked.

## Teardown helpers (`revocation.py`)
- `kill_key_sessions(key_id)` — revoke all of a key's sessions (Redis + DB) and
  invalidate its [[Entitlement]] cache.
- `revoke_user(user_id)` — subscriptions → revoked, keys disabled, sessions
  killed. Used by the admin [[Bot Commands|/revoke]] command.

Because killing a session deletes its Redis state, protected calls stop honoring
the token within the [[Entitlement]] cache window even if the JWT hasn't expired.

## Renewal nuance
Since expiry disables keys, a renewing user gets their **same key reactivated**
(no surprise rotation); only an explicit [[Bot Commands|/key]] reissue rotates.

## Expiry reminders
A separate sweep (every `EXPIRY_REMINDER_MINUTES`, default 60) DMs users **before**
they lapse. `EXPIRY_REMINDER_DAYS` (default `3,1`) defines non-overlapping
days-left bands; a sub gets one localized nudge per band, deduped by a Redis
marker `reminder:<sub_id>:<days>` (TTL outlives the band so a renewed sub can be
reminded again later). Best-effort — a failed DM never stops the sweep.

## Other worker jobs
- [[Notion Sync]] reconcile + two-way action apply (when enabled).
