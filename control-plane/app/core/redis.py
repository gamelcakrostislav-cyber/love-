"""Shared async Redis client.

Redis holds live session state, rate-limit buckets, IP-velocity trails, and the
short-TTL entitlement cache — anything that must be read on the hot path without
hitting Postgres.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

redis_client: aioredis.Redis = aioredis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
)


async def ping() -> bool:
    """Return True if Redis is reachable (used by the health-check)."""
    return bool(await redis_client.ping())
