"""Checkout orchestration.

Phase 5 creates the pending `payments` row and returns a placeholder pay URL so
the bot's `/buy` flow is complete end-to-end. Phase 6 swaps the internals to
call the real `PaymentProvider` (Crypto Pay) for the invoice + pay URL, keyed by
the provider's invoice id.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.user import User
from app.services.audit import record_audit


async def start_checkout(
    db: AsyncSession, *, user: User, plan: Plan
) -> tuple[Payment, str]:
    """Create a pending payment and return (payment, pay_url)."""
    external_id = f"stub-{uuid.uuid4().hex}"  # Phase 6: real provider invoice id
    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        amount=plan.price,
        currency=plan.currency,
        provider="stub",
        external_id=external_id,
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    await db.flush()
    await record_audit(
        db, actor=f"user:{user.id}", action="checkout_started", target=str(payment.id),
        meta={"plan": plan.name, "amount": str(plan.price), "external_id": external_id},
    )
    pay_url = f"https://t.me/CryptoBot?start=invoice_{external_id}"  # placeholder
    return payment, pay_url
