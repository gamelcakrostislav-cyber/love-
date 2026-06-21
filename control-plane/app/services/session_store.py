"""Live session state in Redis.

Redis is authoritative on the hot path: a session is "active" iff its hash key
exists. Revocation (manual, expiry, or eviction) deletes the key, so protected
endpoints stop honoring the token within the cache window — no Postgres hit.
"""

from __future__ import annotations

import time

from app.core import redis_keys
from app.core.config import settings
from app.core.redis import redis_client


async def create(
    *,
    session_id: str,
    key_id: int,
    device_id: int,
    ip: str | None,
    signing_secret: str,
    ttl: int | None = None,
) -> None:
    ttl = ttl or settings.jwt_ttl_seconds
    now = time.time()
    skey = redis_keys.session(session_id)
    idx = redis_keys.key_sessions(key_id)

    pipe = redis_client.pipeline()
    pipe.hset(
        skey,
        mapping={
            "key_id": key_id,
            "device_id": device_id,
            "ip": ip or "",
            "issued_at": now,
            "signing_secret": signing_secret,
        },
    )
    pipe.expire(skey, ttl)
    pipe.zadd(idx, {session_id: now})
    # Keep the index from outliving its members.
    pipe.expire(idx, ttl + 60)
    await pipe.execute()


async def get(session_id: str) -> dict | None:
    data = await redis_client.hgetall(redis_keys.session(session_id))
    return data or None


async def revoke(session_id: str, key_id: int) -> None:
    pipe = redis_client.pipeline()
    pipe.delete(redis_keys.session(session_id))
    pipe.zrem(redis_keys.key_sessions(key_id), session_id)
    await pipe.execute()


async def _prune(key_id: int, ttl: int) -> None:
    """Drop index entries whose sessions have certainly expired by score."""
    cutoff = time.time() - ttl
    await redis_client.zremrangebyscore(redis_keys.key_sessions(key_id), "-inf", cutoff)


async def active_count(key_id: int, ttl: int | None = None) -> int:
    ttl = ttl or settings.jwt_ttl_seconds
    await _prune(key_id, ttl)
    return int(await redis_client.zcard(redis_keys.key_sessions(key_id)))


async def oldest(key_id: int) -> str | None:
    items = await redis_client.zrange(redis_keys.key_sessions(key_id), 0, 0)
    return items[0] if items else None


async def list_sessions(key_id: int) -> list[str]:
    return await redis_client.zrange(redis_keys.key_sessions(key_id), 0, -1)
