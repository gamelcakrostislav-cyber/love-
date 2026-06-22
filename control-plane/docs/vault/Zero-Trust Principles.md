---
tags: [moc, anti-abuse]
---
# Zero-Trust Principles

_Source: `README.md` security notes_

The system never trusts the client. Every entitlement decision is made
server-side; the client can only *request*, the server *decides*.

- **No client-side feature flags** grant access. Access state never lives on, or
  is read from, the client.
- A **leaked credential alone is useless** — a stolen [[API Key]] still has to
  pass [[Device Fingerprint|device]] + concurrency + [[Entitlement]] checks; a
  stolen [[Session Token]] still needs the bound device and a live Redis session.
- **Entitlement is recomputed** at the gateway on every session issue
  ([[Entitlement]]), cached only ~60s so revocation/expiry propagate fast.
- **Payments are verified** before activation — webhook signature + idempotency
  (see [[Payments and Crypto Pay]]).
- **Expiry is server-enforced** by the [[Worker and Expiry|worker]]; the client
  cannot self-extend.
- **Append-only audit log** records every grant, revoke, session issue, and flag.

Related: [[Licensing Model]] · [[Anti-Abuse]]
