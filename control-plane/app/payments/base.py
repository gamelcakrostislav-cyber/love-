"""Payment provider abstraction.

A provider turns a (user, plan) into a payable invoice and verifies the
provider's webhook before anything is activated. Implementations must:
  - sign/verify webhooks (never trust an unverified "paid" call)
  - expose a stable `external_id` (the invoice id) for idempotency
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from app.models.plan import Plan
from app.models.user import User


@dataclass(frozen=True)
class InvoiceResult:
    external_id: str
    pay_url: str


@dataclass(frozen=True)
class WebhookEvent:
    external_id: str
    status: str                      # normalized: "paid" / "failed" / other
    amount: Decimal
    currency: str
    payer_fingerprint: str | None    # payer identity if the provider exposes one


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    async def create_invoice(
        self, user: User, plan: Plan, amount: Decimal | None = None
    ) -> InvoiceResult:
        """Invoice for `plan`. `amount` overrides the plan price (e.g. after a
        promo discount); when None the full `plan.price` is charged."""
        ...

    @abstractmethod
    def verify_webhook(self, body: bytes, signature: str | None) -> bool: ...

    @abstractmethod
    def parse_event(self, payload: dict) -> WebhookEvent | None: ...
