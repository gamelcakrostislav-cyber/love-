"""Typed licensing errors mapped to HTTP responses at the router boundary."""

from __future__ import annotations


class LicensingError(Exception):
    """Base for all entitlement/enforcement failures.

    `code` is a stable machine-readable string; `http_status` is how the gateway
    should surface it. Never leak whether a key exists vs. is unauthorized beyond
    what these codes intentionally reveal.
    """

    code: str = "licensing_error"
    http_status: int = 403

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code


class InvalidKey(LicensingError):
    code = "invalid_key"
    http_status = 401


class KeyDisabled(LicensingError):
    code = "key_disabled"
    http_status = 403


class NoActiveSubscription(LicensingError):
    code = "no_active_subscription"
    http_status = 402


class DeviceLimitReached(LicensingError):
    code = "device_limit_reached"
    http_status = 403


class DeviceInCooldown(LicensingError):
    code = "device_in_cooldown"
    http_status = 403


class ConcurrencyLimit(LicensingError):
    code = "concurrency_limit"
    http_status = 429


class RateLimited(LicensingError):
    code = "rate_limited"
    http_status = 429


class SessionInvalid(LicensingError):
    code = "session_invalid"
    http_status = 401


class ReplayDetected(LicensingError):
    code = "replay_detected"
    http_status = 401
