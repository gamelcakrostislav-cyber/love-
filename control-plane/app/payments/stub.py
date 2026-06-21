"""Offline stub provider for local dev when no Crypto Pay token is configured.

Lets `/buy` complete without network. Real activation in dev happens via admin
`/grant` (Phase 7); this provider's webhook verification always fails closed.
"""

from __future__ import annotations

import uuid

from app.models.plan import Plan
from app.models.user import User
from app.payments.base import InvoiceResult, PaymentProvider, WebhookEvent


class StubProvider(PaymentProvider):
    name = "stub"

    async def create_invoice(self, user: User, plan: Plan) -> InvoiceResult:
        external_id = f"stub-{uuid.uuid4().hex}"
        return InvoiceResult(
            external_id=external_id,
            pay_url=f"https://t.me/CryptoBot?start=invoice_{external_id}",
        )

    def verify_webhook(self, body: bytes, signature: str | None) -> bool:
        return False  # fail closed — no unsigned activation path

    def parse_event(self, payload: dict) -> WebhookEvent | None:
        return None
