"""Checkout orchestration — creates an invoice via the active provider."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.promo_code import PromoCode
from app.models.user import User
from app.payments.factory import get_provider
from app.services.audit import record_audit


async def start_checkout(
    db: AsyncSession,
    *,
    user: User,
    plan: Plan,
    amount: Decimal | None = None,
    promo: PromoCode | None = None,
) -> tuple[Payment, str]:
    """Create a provider invoice + pending payment row. Returns (payment, pay_url).

    `amount` is the total actually charged (defaults to the full plan price);
    pass the discounted amount together with `promo` when a code is applied. The
    promo redemption itself is only recorded once the payment is paid.
    """
    charge = plan.price if amount is None else amount
    provider = get_provider()
    invoice = await provider.create_invoice(user, plan, amount=charge)
    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        amount=charge,
        currency=plan.currency,
        provider=provider.name,
        external_id=invoice.external_id,
        status=PaymentStatus.PENDING,
        promo_code_id=promo.id if promo else None,
    )
    db.add(payment)
    await db.flush()
    await record_audit(
        db, actor=f"user:{user.id}", action="checkout_started", target=str(payment.id),
        meta={"plan": plan.name, "amount": str(charge), "external_id": invoice.external_id,
              "provider": provider.name,
              "promo": promo.code if promo else None},
    )
    return payment, invoice.pay_url
