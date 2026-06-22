---
tags: [moc, ops]
---
# Roadmap

_Source: `README.md` build phases_

The system was built in 8 phases, all complete.

1. **Scaffold** ✅ — structure, `.env.example`, docker-compose, Postgres+Redis, health-check.
2. **DB** ✅ — models + Alembic migration + plan seeder (see [[Data Model]]).
3. **Licensing core** ✅ — key issue/validate, `/auth/session`, device binding, concurrency, rate-limit, stubbed protected endpoint (see [[Licensing Model]]).
4. **Anti-abuse layer** ✅ — fingerprint dedup, [[Impossible Travel]], signed anti-replay, abuse_events, flagging (see [[Anti-Abuse]]).
5. **Bot** ✅ — client commands incl. `/devices` and key reissue; referral capture (see [[Bot Commands]], [[Referral and Rev-Share]]).
6. **Payments** ✅ — provider interface, Crypto Pay, signed + idempotent webhook, activation (see [[Payments and Crypto Pay]]).
7. **Admin + worker** ✅ — admin commands, auto-expiry, session reaping (see [[Worker and Expiry]]).
8. **Tests** ✅ — pytest covering key validation, device-limit, concurrency cap, webhook signature/idempotency, expiry.

## Possible next steps
- CI workflow (Postgres + Redis services) running the suite on push.
- A real product engine behind the stubbed [[API Reference|/v1/opportunities]].
- Referrer payout cycle for `payable` [[Referral and Rev-Share|commissions]].
