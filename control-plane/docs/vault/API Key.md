---
tags: [concept, licensing]
---
# API Key

_Source: `app/core/security.py`, `app/services/keys.py`, `app/models/api_key.py`_

The long-lived credential, issued **once** after payment (or admin
[[Bot Commands|/grant]]). Generated with `secrets.token_urlsafe(32)`.

- Stored as **`sha256(key)` + an 8-char `prefix`** only — the raw value is shown
  exactly once (DM or `/key` reissue). [[Data Model]].
- Validated by hashing the incoming key and matching `key_hash`.
- **Never** used directly against the engine — it is exchanged for a
  [[Session Token]] via the [[Licensing Model|enforcement pipeline]].
- A leaked key alone is useless: it must still pass [[Device Fingerprint]] +
  concurrency + [[Entitlement]] checks ([[Zero-Trust Principles]]).
- States: `active` / `disabled`; plus a `flagged` boolean set by [[Anti-Abuse]].
- Reissue disables the old key; expiry disables it (reactivated on renewal,
  see [[Worker and Expiry]]).
