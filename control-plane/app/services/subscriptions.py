"""Subscription reads. Activation/extension lands in Phase 6 (payments)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SubscriptionStatus
from app.models.plan import Plan
from app.models.subscription import Subscription


async def get_active_with_plan(
    db: AsyncSession, user_id: int
) -> tuple[Subscription, Plan] | None:
    now = datetime.now(UTC)
    row = (
        await db.execute(
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at > now,
            )
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row else None
