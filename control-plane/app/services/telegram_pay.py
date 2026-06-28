"""Settle a native Telegram payment (Stars or card).

Unlike Crypto Pay (verified by a signed webhook on the gateway), native Telegram
payments arrive on the bot's update stream as a `successful_payment` message.
This module records the sale and grants access through the SAME server-side path
as every other activation — idempotent, referral-aware, promo-aware.

Source of truth is what Telegram *actually charged*: the `successful_payment`
carries `total_amount` + `currency`, which we trust over anything we put on the
wire. The invoice `payload` (minted by us, round-tripped byte-for-byte) only maps
the charge back to our plan/promo/method. Accounting is normalized to USD:
  - card  → USD cents / 100
  - Stars → stars / usd_to_stars  (the effective USD value collected)
so revenue and referral commissions are always derived from the real take. The
declared method must match the charged currency (defense in depth).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services import activation, promos, referrals, users

_PREFIX = "tg"
_SEP = "|"

STARS_CURRENCY = "XTR"
# Which currency each method must settle in — reject a payload/charge mismatch.
_METHOD_CURRENCY = {"telegram_stars": STARS_CURRENCY, "telegram_card": "USD"}


@dataclass(frozen=True)
class _Payload:
    plan_id: int
    method: str               # "telegram_stars" | "telegram_card"
    promo_code_id: int | None


def build_payload(*, plan_id: int, method: str, promo_code_id: int | None) -> str:
    """Compact invoice payload (<=128 bytes) round-tripped by Telegram. The
    amount is NOT encoded — it comes from Telegram's charged total at settle."""
    return _SEP.join([_PREFIX, str(plan_id), method, str(promo_code_id or "-")])


def parse_payload(raw: str) -> _Payload | None:
    parts = (raw or "").split(_SEP)
    if len(parts) != 4 or parts[0] != _PREFIX:
        return None
    try:
        return _Payload(
            plan_id=int(parts[1]),
            method=parts[2],
            promo_code_id=int(parts[3]) if parts[3] != "-" else None,
        )
    except ValueError:
        return None


def charged_usd(*, total_amount: int, currency: str, usd_to_stars: int) -> Decimal:
    """USD value of the charge Telegram reports (cents for fiat, Stars/rate for XTR)."""
    if currency == STARS_CURRENCY:
        return (Decimal(total_amount) / Decimal(usd_to_stars)).quantize(Decimal("0.01"))
    return (Decimal(total_amount) / 100).quantize(Decimal("0.01"))


async def _already(db: AsyncSession, *, user_id: int, telegram_id: int, plan_name: str
                   ) -> activation.ActivationResult:
    sub = await db.scalar(
        select(Subscription).where(Subscription.user_id == user_id)
        .order_by(Subscription.expires_at.desc()).limit(1)
    )
    return activation.ActivationResult(
        user_id=user_id, telegram_id=telegram_id, plan_name=plan_name,
        expires_at=sub.expires_at if sub else datetime.now(UTC),
        new_key_raw=None, already_processed=True,
    )


async def settle(
    db: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    charge_id: str,
    payload: str,
    total_amount: int,
    currency: str,
) -> activation.ActivationResult | None:
    """Record a paid native invoice and grant access, idempotently.

    Dedup is by `charge_id` (Telegram's unique payment id) stored as the
    Payment external_id. The booked USD is derived from the charged amount."""
    from app.core.config import settings

    info = parse_payload(payload)
    if info is None:
        return None
    # The declared method must match the currency Telegram actually charged.
    if _METHOD_CURRENCY.get(info.method) != currency:
        return None
    user, _ = await users.get_or_create(db, telegram_id=telegram_id, username=username)
    plan = await db.get(Plan, info.plan_id)
    if plan is None:
        return None
    uid, pname = user.id, plan.name

    usd_amount = charged_usd(
        total_amount=total_amount, currency=currency, usd_to_stars=settings.usd_to_stars)

    existing = await db.scalar(select(Payment).where(Payment.external_id == charge_id))
    if existing is not None:
        return await _already(db, user_id=uid, telegram_id=user.telegram_id, plan_name=pname)

    payment = Payment(
        user_id=uid, plan_id=plan.id, amount=usd_amount, currency="USD",
        provider=info.method, external_id=charge_id, status=PaymentStatus.PAID,
        promo_code_id=info.promo_code_id,
    )
    db.add(payment)
    try:
        await db.flush()
    except IntegrityError:
        # Concurrent re-delivery won the race on the unique external_id — no-op.
        await db.rollback()
        return await _already(db, user_id=uid, telegram_id=telegram_id, plan_name=pname)

    result = await activation.grant(db, user=user, plan=plan, payment=payment, actor="system")

    if info.promo_code_id is not None:
        await promos.record_redemption(
            db, promo_id=info.promo_code_id, user_id=uid, payment_id=payment.id)
    await referrals.qualify_on_payment(
        db, referred_user_id=uid, payment_id=payment.id, amount=usd_amount, currency="USD")
    return result


async def grant_free(
    db: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    plan_id: int,
    promo_code_id: int | None,
) -> activation.ActivationResult | None:
    """Activate a plan a 100%-off promo made free — no invoice, no referral
    commission (zero revenue). Idempotent per (plan, promo, user)."""
    user, _ = await users.get_or_create(db, telegram_id=telegram_id, username=username)
    plan = await db.get(Plan, plan_id)
    if plan is None:
        return None
    charge_id = f"free:{plan_id}:{promo_code_id or '-'}:{user.id}"
    uid, tid, pname = user.id, user.telegram_id, plan.name
    existing = await db.scalar(select(Payment).where(Payment.external_id == charge_id))
    if existing is not None:
        return await _already(db, user_id=uid, telegram_id=tid, plan_name=pname)

    payment = Payment(
        user_id=user.id, plan_id=plan.id, amount=Decimal("0.00"), currency="USD",
        provider="promo_free", external_id=charge_id, status=PaymentStatus.PAID,
        promo_code_id=promo_code_id,
    )
    db.add(payment)
    try:
        await db.flush()
    except IntegrityError:
        # Concurrent double-tap won the race on the unique charge id — no-op.
        await db.rollback()
        return await _already(db, user_id=uid, telegram_id=tid, plan_name=pname)
    result = await activation.grant(db, user=user, plan=plan, payment=payment, actor="system")
    if promo_code_id is not None:
        await promos.record_redemption(
            db, promo_id=promo_code_id, user_id=user.id, payment_id=payment.id)
    return result
