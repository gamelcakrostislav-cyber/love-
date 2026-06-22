---
tags: [licensing, payments]
---
# Data Model

_Source: `app/models/*`, `migrations/versions/0001_initial.py`_

PostgreSQL is the system of record; live state is mirrored in Redis.

## Tables

| Table | Purpose | Key columns |
|---|---|---|
| `users` | accounts | `telegram_id` (unique), `risk_score`, `is_blogger`, `referred_by` |
| `plans` | catalog | `price`, `duration_days`, `rate_limit_per_min`, `max_devices`, `max_concurrent_sessions`, `is_trial`, `max_profitability` → [[Plans and Pricing]] |
| `subscriptions` | grants | `status` (active/expired/revoked/suspended), `expires_at`, `payment_id` |
| `api_keys` | [[API Key]] | `key_hash` (sha256 only), `prefix`, `status`, `flagged` |
| `devices` | [[Device Fingerprint]] | `fingerprint`, `status`, `cooldown_until`; unique `(key_id, fingerprint)` |
| `sessions` | [[Session Token]] history | `id` (uuid), `device_id`, `ip`, `expires_at`, `revoked` |
| `payments` | invoices | `external_id` (unique → idempotency), `payer_fingerprint`, `status` |
| `referrals` | invite edges | `referrer_user_id`, `referred_user_id` (unique), `rate`, `status` → [[Referral and Rev-Share]] |
| `commissions` | rewards | `payment_id` (unique), `rate`, `amount`, `status` |
| `abuse_events` | detections | `type`, `detail` → [[Anti-Abuse]] |
| `audit_log` | append-only | `actor`, `action`, `target`, `meta` (JSONB) |

## Notes
- Only `sha256(key)` + an 8-char `prefix` are stored for keys — the raw key is
  shown once. See [[API Key]].
- `payments.external_id` and `commissions.payment_id` are **unique** so a replayed
  webhook can't extend a sub twice or double-credit a referrer.
- `plans.max_profitability` gates the trial tier server-side (trial = `0.0200`).
