---
tags: [concept, anti-abuse, api]
---
# Nonce

_Source: `app/services/antireplay.py`, `app/core/security.py`, `app/gateway/deps.py`_

A single-use random value that makes signed protected requests **non-replayable**.

Protected calls carry `X-Timestamp`, `X-Nonce`, `X-Signature`
([[API Reference]]). The signature is an HMAC over
`timestamp · nonce · method · path · sha256(body)` keyed by the per-session
**signing secret** (delivered once at `/auth/session`, never re-sent).

- The nonce is stored in Redis with `SET NX` (atomic check-and-store) — a repeat
  is a replay and is rejected.
- The timestamp must be within `REQUEST_SIGNATURE_MAX_SKEW` seconds.
- Net effect: a passively sniffed request can't be replayed (nonce consumed +
  stale timestamp), and a sniffed [[Session Token]] alone can't forge new
  requests (no signing secret) — [[Zero-Trust Principles]].

Implemented as `consume_nonce()`; see [[Anti-Abuse]].
