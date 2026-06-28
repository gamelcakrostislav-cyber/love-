"""Settle a native Telegram payment (Stars or card).

Unlike Crypto Pay (verified by a signed webhook on the gateway), native Telegram
payments arrive on the bot's update stream as a `successful_payment` message.
This module records the sale and grants access through the SAME server-side path
as every other activation — idempotent, referral-aware, promo-aware.

We trust Telegram's processed payment: the amount/currency are whatever Telegram
charged, and the invoice `payload` (which we minted and Telegram round-trips) maps
it back to our plan/promo. Accounting is normalized to USD (the Stars price is
just a presentation of the USD value) so revenue and commissions stay in one unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import UTC, datetime

from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services import activation, promos, referrals, users

_PREFIX = "tg"
_SEP = "|"


@dataclass(frozen=True)
class _Payload:
    plan_id: int
    method: str               # "telegram_stars" | "telegram_card"
    promo_code_id: int | None
    usd_cents: int


def build_payload(*, plan_id: int, method: str, promo_code_id: int | None, usd_cents: int) -> str:
    """Compact invoice payload (<=128 bytes) round-tripped by Telegram."""
    return _SEP.join(
        [_PREFIX, str(plan_id), method, str(promo_code_id or "-"), str(usd_cents)]
    )


def parse_payload(raw: str) -> _Payload | None:
    parts = (raw or "").split(_SEP)
    if len(parts) != 5 or parts[0] != _PREFIX:
        return None
    try:
        return _Payload(
            plan_id=int(parts[1]),
            method=parts[2],
            promo_code_id=int(parts[3]) if parts[3] != "-" else None,
            usd_cents=int(parts[4]),
        )
    except ValueError:
        return None


async def settle(
    db: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    charge_id: str,
    payload: str,
) -> activation.ActivationResult | None:
    """Idempotently record a paid native invoice and grant access.

    Dedupe is by `charge_id` (Telegram's unique payment id) stored as the
    Payment's external_id — a duplicate delivery is a no-op."""
    info = parse_payload(payload)
    if info is None:
        return None
    user, _ = await users.get_or_create(db, telegram_id=telegram_id, username=username)
    plan = await db.get(Plan, info.plan_id)
    if plan is None:
        return None

    usd_amount = (Decimal(info.usd_cents) / 100).quantize(Decimal("0.01"))

    existing = await db.scalar(select(Payment).where(Payment.external_id == charge_id))
    if existing is not None and existing.status == PaymentStatus.PAID:
        # Already settled (duplicate delivery) — no-op so the caller skips the DM.
        sub = await db.scalar(
            select(Subscription).where(Subscription.user_id == user.id)
            .order_by(Subscription.expires_at.desc()).limit(1)
        )
        return activation.ActivationResult(
            user_id=user.id, telegram_id=user.telegram_id, plan_name=plan.name,
            expires_at=sub.expires_at if sub else datetime.now(UTC),
            new_key_raw=None, already_processed=True,
        )

    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        amount=usd_amount,
        currency="USD",
        provider=info.method,
        external_id=charge_id,
        status=PaymentStatus.PAID,
        promo_code_id=info.promo_code_id,
    )
    db.add(payment)
    await db.flush()

    result = await activation.grant(db, user=user, plan=plan, payment=payment, actor="system")

    if info.promo_code_id is not None:
        await promos.record_redemption(
            db, promo_id=info.promo_code_id, user_id=user.id, payment_id=payment.id
        )
    await referrals.qualify_on_payment(
        db, referred_user_id=user.id, payment_id=payment.id,
        amount=usd_amount, currency="USD",
    )
    return result
