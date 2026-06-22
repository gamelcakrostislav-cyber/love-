---
tags: [moc, ops]
---
# Architecture

_Source: `README.md`, `docker-compose.yml`, `app/` layout_

Three processes share one codebase (`app/core`, `app/models`, `app/services`) so
licensing logic lives in exactly one place.

| Service    | Role |
|------------|------|
| `gateway`  | FastAPI — [[API Reference\|/auth/session]], protected engine, payment webhook |
| `bot`      | aiogram 3.x — client + admin commerce ([[Bot Commands]]) |
| `worker`   | APScheduler — subscription expiry + session reaping ([[Worker and Expiry]]) |
| `postgres` | system of record ([[Data Model]]) |
| `redis`    | live [[Session Token\|sessions]], rate-limit buckets, IP velocity, [[Entitlement]] cache |

## Request / data flow

```mermaid
flowchart TD
    U[Client / SDK] -->|API key + fingerprint| G[Gateway: /auth/session]
    G -->|recompute entitlement| PG[(Postgres)]
    G -->|mirror session| R[(Redis)]
    G -->|short-lived token + signing secret| U
    U -->|token + signed request| P[Gateway: /v1/opportunities]
    P -->|verify JWT + live session| R
    P -->|tier-filtered mock data| U
    B[Bot] --> PG
    CB[Crypto Pay] -->|signed webhook| W[Gateway: /webhooks/cryptopay]
    W --> PG
    WK[Worker] -->|expire + reap every 60s| PG
    WK --> R
```

See [[Licensing Model]] for the enforcement pipeline and [[Zero-Trust Principles]]
for why nothing is trusted from the client.
