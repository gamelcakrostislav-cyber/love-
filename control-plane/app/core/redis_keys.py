"""Centralized Redis key naming so every module agrees on the layout."""

from __future__ import annotations


def session(session_id: str) -> str:
    """Hash holding live session state; TTL = token lifetime."""
    return f"sess:{session_id}"


def key_sessions(key_id: int) -> str:
    """Sorted set of a key's active session ids, scored by issue time."""
    return f"key:{key_id}:sessions"


def entitlement(key_id: int) -> str:
    """Short-TTL cache of the server-computed entitlement snapshot."""
    return f"ent:{key_id}"


def ratelimit(key_id: int) -> str:
    """Token-bucket hash for per-key rate limiting."""
    return f"rl:{key_id}"


def key_ips(key_id: int) -> str:
    """Recent session IP trail for velocity / impossible-travel checks."""
    return f"key:{key_id}:ips"


def nonce(value: str) -> str:
    """Seen-nonce marker for anti-replay on signed protected requests."""
    return f"nonce:{value}"
