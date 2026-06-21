"""Server-side entitlement: the single source of truth for what a key may do.

Recomputed from Postgres on every session issue and cached in Redis with a short
TTL (~60s) so protected endpoints stay fast while revocation propagates within
the cache window. Nothing about access state is ever read from the client.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys
from app.core.config import settings
from app.core.redis import redis_client
from app.models.api_key import ApiKey
from app.models.enums import ApiKeyStatus, SubscriptionStatus
from app.models.plan import Plan
from app.models.subscription import Subscription


class Entitlement(BaseModel):
    key_id: int
    user_id: int
    plan_name: str
    is_trial: bool
    rate_limit_per_min: int
    max_devices: int
    max_concurrent_sessions: int
    # None => no profitability cap (sees all opportunities).
    max_profitability: float | None
    expires_at: datetime


def build(key: ApiKey, subscription: Subscription, plan: Plan) -> Entitlement:
    return Entitlement(
        key_id=key.id,
        user_id=key.user_id,
        plan_name=plan.name,
        is_trial=plan.is_trial,
        rate_limit_per_min=plan.rate_limit_per_min,
        max_devices=plan.max_devices,
        max_concurrent_sessions=plan.max_concurrent_sessions,
        max_profitability=float(plan.max_profitability) if plan.max_profitability is not None else None,
        expires_at=subscription.expires_at,
    )


async def cache_set(ent: Entitlement) -> None:
    await redis_client.set(
        redis_keys.entitlement(ent.key_id),
        ent.model_dump_json(),
        ex=settings.entitlement_cache_ttl,
    )


async def cache_get(key_id: int) -> Entitlement | None:
    raw = await redis_client.get(redis_keys.entitlement(key_id))
    return Entitlement.model_validate_json(raw) if raw else None


async def invalidate(key_id: int) -> None:
    await redis_client.delete(redis_keys.entitlement(key_id))


async def recompute(db: AsyncSession, key_id: int) -> Entitlement | None:
    """Authoritative recompute from Postgres. Returns None if not entitled."""
    now = datetime.now(UTC)
    row = (
        await db.execute(
            select(ApiKey, Subscription, Plan)
            .join(Subscription, Subscription.user_id == ApiKey.user_id)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(
                ApiKey.id == key_id,
                ApiKey.status == ApiKeyStatus.ACTIVE,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at > now,
            )
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    key, subscription, plan = row
    ent = build(key, subscription, plan)
    await cache_set(ent)
    return ent


async def get(db: AsyncSession, key_id: int) -> Entitlement | None:
    """Cache-first read used on the protected hot path."""
    cached = await cache_get(key_id)
    if cached is not None:
        return cached
    return await recompute(db, key_id)
