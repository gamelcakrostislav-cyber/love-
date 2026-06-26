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


def support_history(telegram_id: int) -> str:
    """Recent AI-support conversation turns for a user (JSON list)."""
    return f"support:hist:{telegram_id}"


def support_human(telegram_id: int) -> str:
    """Flag: user is in human-handoff mode (messages relayed to admins)."""
    return f"support:human:{telegram_id}"


def support_ratelimit(telegram_id: int) -> str:
    """Per-user counter capping AI-support calls per minute."""
    return f"support:rl:{telegram_id}"


def sync_lock(name: str) -> str:
    """Mutex so only one reconcile run (e.g. Notion) is in flight at a time."""
    return f"lock:sync:{name}"


def expiry_reminder(subscription_id: int, days: int) -> str:
    """Marker that a 'expires in <days>' reminder was already sent for a sub."""
    return f"reminder:{subscription_id}:{days}"


def winback(user_id: int) -> str:
    """Marker that a win-back nudge was already sent to a lapsed user."""
    return f"winback:{user_id}"


def abuse_alert_watermark() -> str:
    """Highest AbuseEvent id already alerted to admins (so we only alert new ones)."""
    return "abuse:alert:watermark"


def drip(user_id: int, day: int) -> str:
    """Marker that the day-<day> onboarding nudge was sent to a user."""
    return f"drip:{user_id}:{day}"


def digest(user_id: int) -> str:
    """Marker (7-day TTL) that this user already got their weekly digest."""
    return f"digest:{user_id}"


def milestone(user_id: int) -> str:
    """Highest referral milestone already celebrated for a referrer."""
    return f"growth:milestone:{user_id}"


def feedback_mode(telegram_id: int) -> str:
    """Flag: the user's next message should be captured as feedback (short TTL)."""
    return f"feedback:mode:{telegram_id}"


def promo_armed(telegram_id: int) -> str:
    """The promo code a user applied via /promo, used on their next purchase."""
    return f"promo:armed:{telegram_id}"
