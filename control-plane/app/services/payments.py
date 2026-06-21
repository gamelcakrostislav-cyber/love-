"""Checkout orchestration — creates an invoice via the active provider."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.user import User
from app.payments.factory import get_provider
from app.services.audit import record_audit


async def start_checkout(
    db: AsyncSession, *, user: User, plan: Plan
) -> tuple[Payment, str]:
    """Create a provider invoice + pending payment row. Returns (payment, pay_url)."""
    provider = get_provider()
    invoice = await provider.create_invoice(user, plan)
    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        amount=plan.price,
        currency=plan.currency,
        provider=provider.name,
        external_id=invoice.external_id,
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    await db.flush()
    await record_audit(
        db, actor=f"user:{user.id}", action="checkout_started", target=str(payment.id),
        meta={"plan": plan.name, "amount": str(plan.price), "external_id": invoice.external_id,
              "provider": provider.name},
    )
    return payment, invoice.pay_url
