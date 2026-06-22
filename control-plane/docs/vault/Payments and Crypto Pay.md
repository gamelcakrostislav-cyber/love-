---
tags: [payments]
---
# Payments and Crypto Pay

_Source: `app/payments/*`, `app/services/{payments,activation}.py`, `app/gateway/routers/webhooks.py`_

## Provider abstraction
`PaymentProvider` (`app/payments/base.py`) — `create_invoice`, `verify_webhook`,
`parse_event`. Implementations:
- **`CryptoPayProvider`** (@CryptoBot) — default; fiat USD invoices.
- **`StubProvider`** — offline dev when no token; fails webhook verification closed.

`factory.get_provider()` picks Crypto Pay when `CRYPTOPAY_API_TOKEN` is set, else stub.

## Checkout
`/buy` → `payments.start_checkout()` creates a provider invoice + a `pending`
[[Data Model|payment]] row keyed by the provider `external_id`.

## Webhook — `POST /webhooks/cryptopay`
1. **Verify signature first** — `HMAC_SHA256(body, key=SHA256(api_token))` vs the
   `crypto-pay-api-signature` header. A forged/unsigned call grants nothing
   ([[Zero-Trust Principles]]).
2. **Idempotent** — deduped by `external_id`; replays are no-ops.
3. **Activate** (`activation.activate_paid_payment`):
   - mark paid → create/extend [[Entitlement|subscription]] (`+duration_days`)
   - issue [[API Key]] once (DM'd) or reactivate a disabled one
   - record `payer_fingerprint` + multi-account linkage ([[Anti-Abuse]])
   - unlock [[Referral and Rev-Share|referral commission]]
   - invalidate the [[Entitlement]] cache

`activation.grant()` is reused by the admin [[Bot Commands|/grant]] command.

> Note: Crypto Pay doesn't expose a payer wallet, so `payer_fingerprint` is `None`
> for it; the linkage logic populates for any provider that does.
