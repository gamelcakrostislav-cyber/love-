"""Subscription activation — the only path that grants paid access.

Used by the payment webhook (after signature verification) and reused by admin
`/grant`. Everything here is server-side and idempotent:
  - paid payments are deduped by `external_id` (replays are no-ops)
  - subscriptions extend from the later of now / current expiry
  - a key is issued only if the user has no active one (else reactivated)
  - payer fingerprint is linked for multi-account detection
  - referral commission is unlocked (idempotent per payment)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.enums import ApiKeyStatus, PaymentStatus, SubscriptionStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services import abuse, entitlements, keys, promos, referrals
from app.services.audit import record_audit


@dataclass
class ActivationResult:
    user_id: int
    telegram_id: int
    plan_name: str
    expires_at: datetime
    new_key_raw: str | None  # set only when a fresh key was issued (DM once)
    already_processed: bool


async def _grant_subscription(
    db: AsyncSession, *, user: User, plan: Plan, payment_id: int | None
) -> Subscription:
    """Create or extend the user's active subscription for `plan.duration_days`."""
    now = datetime.now(UTC)
    sub = await db.scalar(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    delta = timedelta(days=plan.duration_days)
    if sub is not None:
        sub.expires_at = sub.expires_at + delta
        sub.plan_id = plan.id
        if payment_id is not None:
            sub.payment_id = payment_id
    else:
        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            expires_at=now + delta,
            payment_id=payment_id,
        )
        db.add(sub)
    await db.flush()
    return sub


async def _ensure_key(db: AsyncSession, user: User) -> tuple[ApiKey, str | None]:
    """Return the user's key, reactivating a disabled one or issuing a fresh one.

    Since expiry disables keys, a renewing user gets their *same* key reactivated
    (no surprise rotation); only an explicit `/key` reissue rotates. A brand-new
    customer gets a freshly issued key whose raw value is DM'd once.
    """
    most_recent = await db.scalar(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()).limit(1)
    )
    if most_recent is not None and most_recent.status == ApiKeyStatus.ACTIVE:
        return most_recent, None
    if most_recent is not None and most_recent.status == ApiKeyStatus.DISABLED:
        most_recent.status = ApiKeyStatus.ACTIVE
        await record_audit(
            db, actor="system", action="key_reactivated", target=str(most_recent.id),
            meta={"user_id": user.id},
        )
        return most_recent, None
    key, raw = await keys.issue(db, user.id)
    return key, raw


async def grant(
    db: AsyncSession,
    *,
    user: User,
    plan: Plan,
    payment: Payment | None = None,
    actor: str = "system",
) -> ActivationResult:
    """Grant/extend access. Shared by webhook activation and admin /grant."""
    sub = await _grant_subscription(
        db, user=user, plan=plan, payment_id=payment.id if payment else None
    )
    key, raw = await _ensure_key(db, user)
    await entitlements.invalidate(key.id)
    await record_audit(
        db, actor=actor, action="subscription_granted", target=str(user.id),
        meta={"plan": plan.name, "expires_at": sub.expires_at.isoformat(),
              "payment_id": payment.id if payment else None},
    )
    return ActivationResult(
        user_id=user.id,
        telegram_id=user.telegram_id,
        plan_name=plan.name,
        expires_at=sub.expires_at,
        new_key_raw=raw,
        already_processed=False,
    )


async def activate_paid_payment(
    db: AsyncSession,
    *,
    external_id: str,
    payer_fingerprint: str | None,
    amount: Decimal | None = None,
) -> ActivationResult | None:
    """Idempotently process a verified 'paid' webhook for `external_id`."""
    payment = await db.scalar(select(Payment).where(Payment.external_id == external_id))
    if payment is None:
        return None  # unknown invoice — ignore

    user = await db.get(User, payment.user_id)
    plan = await db.get(Plan, payment.plan_id)
    if user is None or plan is None:
        return None

    # Idempotency: a replayed webhook for an already-paid invoice is a no-op.
    if payment.status == PaymentStatus.PAID:
        sub = await db.scalar(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        return ActivationResult(
            user_id=user.id, telegram_id=user.telegram_id, plan_name=plan.name,
            expires_at=sub.expires_at if sub else datetime.now(UTC),
            new_key_raw=None, already_processed=True,
        )

    payment.status = PaymentStatus.PAID
    if payer_fingerprint:
        payment.payer_fingerprint = payer_fingerprint

    result = await grant(db, user=user, plan=plan, payment=payment, actor="system")

    # Payer identity reused across accounts -> flag (multi-account linkage).
    if payer_fingerprint:
        await abuse.link_payer_fingerprint(db, user_id=user.id, payer_fingerprint=payer_fingerprint)

    # Record the promo redemption (idempotent, one per user+code) now that the
    # discounted invoice is actually paid.
    if payment.promo_code_id is not None:
        await promos.record_redemption(
            db, promo_id=payment.promo_code_id, user_id=user.id, payment_id=payment.id
        )

    # Unlock referral commission now that the referred user has paid.
    await referrals.qualify_on_payment(
        db, referred_user_id=user.id, payment_id=payment.id,
        amount=amount if amount is not None else payment.amount,
        currency=payment.currency,
    )
    return result
