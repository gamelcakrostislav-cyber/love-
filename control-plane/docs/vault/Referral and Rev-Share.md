---
tags: [payments]
---
# Referral and Rev-Share

_Source: `app/services/referrals.py`_

Inviters earn a commission when the people they refer subscribe.

## Rates
- **Standard referrer: 20%** (≈ $10 monthly, $100 yearly).
- **Blogger referrer: 30%** (`is_blogger` on the user; +10 points so a traffic
  reseller can use the blogger's funnel).
- The rate is **snapshotted** on the referral edge at attach time.

## Rules (anti-abuse)
- **One referrer per referred user**; **no self-referral**.
- Captured on `/start <inviter_telegram_id>` deep-link ([[Bot Commands]]).
- **Reward unlocks only when the referred user actually pays** — `attach()`
  creates a `pending` edge; `qualify_on_payment()` flips it to `qualified` and
  creates a `payable` commission, called from [[Payments and Crypto Pay|activation]].
- **Idempotent** per payment via the unique `commissions.payment_id` — a replayed
  webhook can't double-credit.
- Effectively **capped per identity cluster**: a referrer is never paid for an
  account that hasn't paid, neutralizing self-referral farming ([[Anti-Abuse]]).

See `referrals` + `commissions` in [[Data Model]].
