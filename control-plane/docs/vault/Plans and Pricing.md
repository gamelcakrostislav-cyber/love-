---
tags: [licensing]
---
# Plans and Pricing

_Source: `scripts/seed_plans.py`, `app/models/plan.py`_

| Plan | Price | Duration | Entitlement | Devices | Sessions | Rate limit |
|---|---|---|---|---|---|---|
| `trial` | free | 7 days | **only ≤2% profitability** opportunities | 1 | 1 | 10/min |
| `monthly` | $49 | 30 days | **all** opportunities | 2 | 2 | 120/min |
| `yearly` | $479 | 365 days | **all** opportunities | 3 | 2 | 120/min |

## Trial gating
`plans.max_profitability` caps what the protected endpoint returns. Trial =
`0.0200` → only opportunities with profitability ≤ 2% are visible; paid plans
have no cap (sees all). The filter is applied **server-side** in the mock engine
(`app/gateway/mock_engine.py`) — the client cannot influence it
([[Zero-Trust Principles]]).

These limits flow into the [[Entitlement]] snapshot used by the
[[Licensing Model|enforcement pipeline]] and [[Anti-Abuse]] caps.

Seeded idempotently on gateway startup; see [[Runbook]].
Purchasing happens via [[Bot Commands|/buy]] → [[Payments and Crypto Pay]].
