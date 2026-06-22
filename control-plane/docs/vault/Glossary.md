---
tags: [moc, concept]
---
# Glossary

One-line definitions. Core concepts have their own notes (linked).

- **[[API Key]]** — long-lived credential, issued once; stored only as a hash.
- **[[Session Token]]** — short-lived device-bound JWT; the only thing the engine accepts.
- **[[Device Fingerprint]]** — stable client id binding a session to a machine.
- **[[Entitlement]]** — server-computed snapshot of what a key may do.
- **[[Impossible Travel]]** — geo-velocity risk signal across sessions.
- **[[Nonce]]** — single-use value for signed-request anti-replay.
- **Concurrency cap** — max simultaneous sessions per key; overflow evicts oldest. → [[Anti-Abuse]]
- **Cooldown** — 24h wait before a new device beyond the limit auto-approves. → [[Device Fingerprint]]
- **Flag** — soft anomaly state (`api_keys.flagged`); surfaced to admin, not a ban. → [[Anti-Abuse]]
- **Risk score** — accumulating per-user risk weight bumped by detections.
- **Idempotency** — webhook deduped by `external_id` so replays don't double-grant. → [[Payments and Crypto Pay]]
- **Payer fingerprint** — payer identity for cross-account payment linkage.
- **Commission** — referrer reward, unlocked only when the referred user pays. → [[Referral and Rev-Share]]
- **Audit log** — append-only record of grants, revokes, session issues, flags.
- **Entitlement cache** — ~60s Redis cache so revocation propagates fast.
- **Token bucket** — Redis rate-limit algorithm, capacity from the plan.
- **MOC** — *Map of Content*, an index note (this vault uses `#moc`). Start at [[Home]].
