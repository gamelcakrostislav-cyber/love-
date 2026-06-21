"""Small async helpers to build test fixtures directly via the ORM."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PaymentStatus, SubscriptionStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services import keys


async def make_user(db: AsyncSession, telegram_id: int = 1001, **kw) -> User:
    user = User(telegram_id=telegram_id, username=kw.get("username"))
    db.add(user)
    await db.flush()
    return user


async def make_plan(
    db: AsyncSession,
    *,
    name: str = "monthly",
    price: str = "49.00",
    duration_days: int = 30,
    rate_limit_per_min: int = 120,
    max_devices: int = 1,
    max_concurrent_sessions: int = 1,
    is_trial: bool = False,
    max_profitability: str | None = None,
) -> Plan:
    plan = Plan(
        name=name,
        price=Decimal(price),
        currency="USD",
        duration_days=duration_days,
        rate_limit_per_min=rate_limit_per_min,
        max_devices=max_devices,
        max_concurrent_sessions=max_concurrent_sessions,
        is_trial=is_trial,
        max_profitability=Decimal(max_profitability) if max_profitability else None,
    )
    db.add(plan)
    await db.flush()
    return plan


async def make_subscription(
    db: AsyncSession, *, user: User, plan: Plan, days_left: int = 30
) -> Subscription:
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        expires_at=datetime.now(UTC) + timedelta(days=days_left),
    )
    db.add(sub)
    await db.flush()
    return sub


async def make_key(db: AsyncSession, *, user: User) -> tuple[int, str]:
    """Issue an API key; return (key_id, raw_key)."""
    key, raw = await keys.issue(db, user.id)
    await db.flush()
    return key.id, raw


async def make_payment(
    db: AsyncSession, *, user: User, plan: Plan, external_id: str, status=PaymentStatus.PENDING
) -> Payment:
    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        amount=plan.price,
        currency=plan.currency,
        provider="cryptopay",
        external_id=external_id,
        status=status,
    )
    db.add(payment)
    await db.flush()
    return payment
