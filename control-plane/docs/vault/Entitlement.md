---
tags: [concept, licensing]
---
# Entitlement

_Source: `app/services/entitlements.py`_

The single server-side source of truth for what a key may do. **Recomputed from
Postgres on every session issue** and cached in Redis with a short TTL
(`ENTITLEMENT_CACHE_TTL`, ~60s) so protected calls stay fast while
revocation/expiry propagates within the window.

Snapshot fields: `plan_name`, `is_trial`, `rate_limit_per_min`, `max_devices`,
`max_concurrent_sessions`, `max_profitability`, `expires_at`.

- Built from the active subscription + [[Plans and Pricing|plan]]; `None` ⇒ not
  entitled (no active/unexpired subscription).
- Drives the [[Licensing Model|enforcement pipeline]] caps and the trial
  profitability filter.
- **Nothing about access state is read from the client** — it is always
  recomputed ([[Zero-Trust Principles]]).
- Invalidated on activation, renewal, and revocation
  ([[Payments and Crypto Pay]], [[Worker and Expiry]]).
