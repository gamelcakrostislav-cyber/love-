---
tags: [anti-abuse]
---
# Anti-Abuse

_Source: `app/services/{abuse,risk,ratelimit,concurrency,devices,antireplay}.py`_

The priority of the whole system. Detections **flag, not ban** — tripping a
threshold sets `api_keys.flagged`, records an `abuse_event`, bumps the user's
`risk_score`, and surfaces to the admin ([[Bot Commands]] `/flags`), but the key
keeps working until an admin acts (low false-positive cost).

## Vector → defense

| Vector | Defense |
|---|---|
| **Key sharing** | [[Device Fingerprint]] binding + 24h cooldown; concurrency cap (evict oldest + log); per-key token-bucket rate limit; signed anti-replay ([[Nonce]]) |
| **Multi-accounting** | fingerprint dedup across accounts → flag cluster; payer-fingerprint linkage at payment ([[Payments and Crypto Pay]]) |
| **[[Impossible Travel]]** | geo velocity between consecutive [[Session Token\|sessions]] → flag above threshold |
| **Subscription bypass** | server-side [[Entitlement]] recompute every session; verified + idempotent webhooks; server-enforced expiry ([[Worker and Expiry]]) |

## Mechanisms
- **Device binding** — each [[API Key]] allows `max_devices`; a new device beyond
  the limit is parked in **cooldown** (24h) then auto-approves. (`devices.py`)
- **Concurrency cap** — `max_concurrent_sessions`; overflow evicts the oldest
  session and logs `concurrency_evict`. (`concurrency.py`)
- **Rate limiting** — Redis token-bucket (Lua), capacity from the plan. (`ratelimit.py`)
- **Anti-replay** — per-session HMAC signature + single-use [[Nonce]] + timestamp
  skew. (`antireplay.py`, `app/gateway/deps.py`)
- **Risk** — [[Impossible Travel]] scoring on the IP trail. (`risk.py`)
- **Flagging** — `flag_key()` sets state + audit. (`abuse.py`)

Grounded in [[Zero-Trust Principles]].
