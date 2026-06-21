"""Crypto Pay (@CryptoBot) provider.

Docs: https://help.crypt.bot/crypto-pay-api
- createInvoice via the API token in the `Crypto-Pay-API-Token` header.
- Webhooks are signed: signature = HMAC_SHA256(body, key=SHA256(api_token)),
  delivered in the `crypto-pay-api-signature` header. We verify it before acting.
"""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.plan import Plan
from app.models.user import User
from app.payments.base import InvoiceResult, PaymentProvider, WebhookEvent

log = get_logger("cryptopay")


class CryptoPayProvider(PaymentProvider):
    name = "cryptopay"

    def __init__(self, token: str | None = None, api_base: str | None = None) -> None:
        self._token = token or settings.cryptopay_api_token
        self._api_base = (api_base or settings.cryptopay_api_base).rstrip("/")

    @property
    def _secret(self) -> bytes:
        # Webhook signing key per Crypto Pay spec.
        return hashlib.sha256(self._token.encode()).digest()

    async def create_invoice(self, user: User, plan: Plan) -> InvoiceResult:
        body = {
            "currency_type": "fiat",
            "fiat": plan.currency,
            "amount": str(plan.price),
            "description": f"{plan.name} subscription",
            # Round-trips back to us in the webhook; we map it to our user/plan.
            "payload": f"user:{user.id}|plan:{plan.id}",
            "allow_anonymous": False,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._api_base}/createInvoice",
                headers={"Crypto-Pay-API-Token": self._token},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"cryptopay createInvoice failed: {data}")
        result = data["result"]
        pay_url = (
            result.get("bot_invoice_url")
            or result.get("mini_app_invoice_url")
            or result.get("pay_url", "")
        )
        return InvoiceResult(external_id=str(result["invoice_id"]), pay_url=pay_url)

    def verify_webhook(self, body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        expected = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_event(self, payload: dict) -> WebhookEvent | None:
        if payload.get("update_type") != "invoice_paid":
            return None
        inv = payload.get("payload") or {}
        invoice_id = inv.get("invoice_id")
        if invoice_id is None:
            return None
        amount = Decimal(str(inv.get("amount", "0")))
        currency = inv.get("fiat") or inv.get("asset") or "USD"
        # Crypto Pay does not expose a payer wallet; payer linkage stays None here.
        payer_fingerprint = inv.get("paid_by") or None
        return WebhookEvent(
            external_id=str(invoice_id),
            status=str(inv.get("status", "")),
            amount=amount,
            currency=currency,
            payer_fingerprint=payer_fingerprint,
        )
