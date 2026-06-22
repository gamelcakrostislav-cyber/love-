---
tags: [concept, licensing]
---
# Session Token

_Source: `app/core/security.py`, `app/services/session_store.py`, `app/gateway/deps.py`_

A short-lived (15 min) server-signed **JWT**, the only credential protected
endpoints accept. Issued by the [[Licensing Model|enforcement pipeline]].

- Claims: `sub` (key id), `sid` (session id), `dfp` (sha256 of
  [[Device Fingerprint]]), `iat`, `exp`, `jti`.
- **Bound to a device** — protected calls must present the matching fingerprint,
  so a sniffed token can't be used elsewhere.
- **Mirrored in Redis** (`sess:{id}`, TTL = token life) — the session must still
  be live, so revocation/expiry propagates within minutes ([[Worker and Expiry]]).
- Carries a per-session **signing secret** for request signing ([[Nonce]]).
- Tracked in a per-key Redis sorted set for the concurrency cap ([[Anti-Abuse]]).
- Refreshed by calling `/auth/session` again ([[API Reference]]).
