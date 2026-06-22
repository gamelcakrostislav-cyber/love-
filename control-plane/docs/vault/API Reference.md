---
tags: [api]
---
# API Reference

_Source: `app/gateway/routers/*`, `app/gateway/deps.py`_

## `POST /auth/session`
Exchange an [[API Key]] for a short-lived [[Session Token]]. The raw key is used
here and nowhere else. Runs the full [[Licensing Model|enforcement pipeline]].

Request:
```json
{ "api_key": "<RAW_KEY>", "device_fingerprint": "device-abc-123" }
```
Response: `token`, `signing_secret`, `expires_at`, `plan`, `rate_limit_per_min`,
`max_profitability`, `evicted_sessions`, `flagged`.

## `GET /v1/opportunities`
The stubbed engine. Accepts **only** the token, never the key. Re-checks the live
session, applies rate limiting, and filters by [[Plans and Pricing|tier]].

Headers: `Authorization: Bearer <TOKEN>`, `X-Device-Fingerprint: <fp>`, plus the
signing headers below.

### Request signing (anti-replay)
When `REQUEST_SIGNING_REQUIRED=true`, send `X-Timestamp`, `X-Nonce`, `X-Signature`:
```
X-Signature = HMAC_SHA256(signing_secret,
    "<timestamp>\n<nonce>\n<METHOD>\n<path>\n<sha256(body)>")
```
The [[Nonce]] is single-use; timestamp must be within `REQUEST_SIGNATURE_MAX_SKEW`.
`scripts/client_example.py` does this end-to-end.

## `POST /webhooks/cryptopay`
Signature-verified, idempotent payment activation → [[Payments and Crypto Pay]].

## `GET /health`
Probes Postgres + Redis; returns `ok` / `degraded`.
