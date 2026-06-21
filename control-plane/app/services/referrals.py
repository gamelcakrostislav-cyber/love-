"""Referral / rev-share logic.

Rules (from planning):
- Standard referrer 20%, blogger 30% (snapshotted on the edge at attach time).
- One referrer per referred user; no self-referral.
- Reward only *unlocks* when the referred user actually pays (qualify), and is
  capped per identity cluster — a referrer is never paid for an account that
  hasn't paid, which neutralizes self-referral farming.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import (
    CommissionStatus,
    ReferralStatus,
    ReferrerType,
)
from app.models.referral import Commission, Referral
from app.models.user import User
from app.services.audit import record_audit


def _rate_for(user: User) -> Decimal:
    rate = settings.referral_rate_blogger if user.is_blogger else settings.referral_rate_standard
    return Decimal(str(rate))


async def attach(
    db: AsyncSession, *, referred_user: User, referrer_telegram_id: int
) -> Referral | None:
    """Create a pending referral edge if eligible; otherwise return None."""
    # Already referred? (one referrer per user)
    existing = await db.scalar(
        select(Referral).where(Referral.referred_user_id == referred_user.id)
    )
    if existing is not None:
        return None

    referrer = await db.scalar(select(User).where(User.telegram_id == referrer_telegram_id))
    if referrer is None or referrer.id == referred_user.id:
        return None  # unknown referrer or self-referral

    referrer_type = ReferrerType.BLOGGER if referrer.is_blogger else ReferrerType.STANDARD
    referral = Referral(
        referrer_user_id=referrer.id,
        referred_user_id=referred_user.id,
        referrer_type=referrer_type,
        rate=_rate_for(referrer),
        status=ReferralStatus.PENDING,
    )
    db.add(referral)
    referred_user.referred_by = referrer.id
    await db.flush()
    await record_audit(
        db, actor=f"user:{referred_user.id}", action="referral_attached",
        target=str(referral.id),
        meta={"referrer_user_id": referrer.id, "rate": str(referral.rate)},
    )
    return referral


async def qualify_on_payment(
    db: AsyncSession, *, referred_user_id: int, payment_id: int, amount: Decimal, currency: str
) -> Commission | None:
    """On the referred user's payment, unlock the referrer's commission.

    Idempotent per payment via the unique `commissions.payment_id` constraint —
    a replayed webhook can't double-credit.
    """
    referral = await db.scalar(
        select(Referral).where(Referral.referred_user_id == referred_user_id)
    )
    if referral is None:
        return None

    # Already credited for this payment?
    dupe = await db.scalar(select(Commission).where(Commission.payment_id == payment_id))
    if dupe is not None:
        return dupe

    if referral.status != ReferralStatus.QUALIFIED:
        referral.status = ReferralStatus.QUALIFIED
        referral.qualified_at = datetime.now(UTC)

    commission = Commission(
        referrer_user_id=referral.referrer_user_id,
        referred_user_id=referred_user_id,
        payment_id=payment_id,
        rate=referral.rate,
        amount=(amount * referral.rate).quantize(Decimal("0.01")),
        currency=currency,
        status=CommissionStatus.PAYABLE,
    )
    db.add(commission)
    await db.flush()
    await record_audit(
        db, actor="system", action="commission_created", target=str(commission.id),
        meta={
            "referrer_user_id": referral.referrer_user_id,
            "payment_id": payment_id,
            "amount": str(commission.amount),
        },
    )
    return commission
