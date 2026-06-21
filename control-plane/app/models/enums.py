"""String enums for status/type columns.

Stored as plain VARCHAR (not native PG enums) to keep migrations simple and
schema changes cheap. Use these constants in code instead of bare strings.
"""

from __future__ import annotations

from enum import StrEnum


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


class ApiKeyStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class DeviceStatus(StrEnum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"  # registered beyond limit; usable after cooldown elapses
    REMOVED = "removed"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


class ReferrerType(StrEnum):
    STANDARD = "standard"
    BLOGGER = "blogger"


class ReferralStatus(StrEnum):
    PENDING = "pending"      # referred user signed up but has not paid yet
    QUALIFIED = "qualified"  # referred user paid -> commission unlocked


class CommissionStatus(StrEnum):
    PENDING = "pending"    # awaiting qualification / payout cycle
    PAYABLE = "payable"    # qualified, ready to pay out
    PAID = "paid"


class AbuseType(StrEnum):
    SHARED_KEY = "shared_key"
    MULTI_ACCOUNT = "multi_account"
    IMPOSSIBLE_TRAVEL = "impossible_travel"
    CONCURRENCY_EVICT = "concurrency_evict"
    DEVICE_LIMIT = "device_limit"
    RATE_LIMIT = "rate_limit"
    REPLAY = "replay"
