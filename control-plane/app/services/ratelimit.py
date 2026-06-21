"""Per-key token-bucket rate limiting in Redis.

Capacity and refill come from the plan (`rate_limit_per_min`). The bucket is
updated atomically via a Lua script so concurrent protected calls can't oversend.
This both protects the engine and caps the value of a shared key.
"""

from __future__ import annotations

import time

from app.core import redis_keys
from app.core.redis import redis_client

# KEYS[1] = bucket hash; ARGV = capacity, refill_per_sec, now, requested
_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed = 0
if tokens >= requested then
  allowed = 1
  tokens = tokens - requested
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
-- Expire idle buckets so they refill to full naturally.
local ttl = math.ceil(capacity / refill) + 60
redis.call('EXPIRE', key, ttl)

return {allowed, tokens}
"""


async def check(key_id: int, rate_per_min: int, *, cost: int = 1) -> tuple[bool, float]:
    """Return (allowed, tokens_remaining). Refills at rate_per_min/60 per second."""
    capacity = max(1, rate_per_min)
    refill_per_sec = capacity / 60.0
    allowed, remaining = await redis_client.eval(
        _BUCKET_LUA,
        1,
        redis_keys.ratelimit(key_id),
        capacity,
        refill_per_sec,
        time.time(),
        cost,
    )
    return bool(int(allowed)), float(remaining)
