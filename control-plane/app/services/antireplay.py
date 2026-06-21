"""Anti-replay nonce store.

A nonce may be used once within the timestamp-skew window. `SET NX` makes the
check-and-store atomic so two concurrent requests can't both consume the same
nonce.
"""

from __future__ import annotations

from app.core import redis_keys
from app.core.config import settings
from app.core.redis import redis_client


async def consume_nonce(nonce: str) -> bool:
    """Return True if the nonce was unseen (now reserved); False if a replay."""
    # TTL only needs to cover the accept window; after that the stale-timestamp
    # check rejects the request anyway, so the marker can expire.
    ttl = settings.request_signature_max_skew * 2 + 1
    stored = await redis_client.set(redis_keys.nonce(nonce), "1", nx=True, ex=ttl)
    return bool(stored)
