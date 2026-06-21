"""Application settings, loaded from environment / .env via pydantic-settings.

Every secret comes from the environment — nothing sensitive is hard-coded or
committed. Import the singleton `settings` everywhere; it is parsed once.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    env: str = "local"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://control:control@postgres:5432/control_plane"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # JWT
    jwt_secret: str = "CHANGE_ME"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 900

    # Caches / anti-replay
    entitlement_cache_ttl: int = 60
    request_signature_max_skew: int = 30
    request_signing_required: bool = True

    # Risk scoring
    impossible_travel_max_kmh: float = 1000.0  # faster than a commercial jet => impossible

    # Device policy
    device_register_cooldown_hours: int = 24

    # Telegram bot
    bot_token: str = "CHANGE_ME"
    admin_ids: set[int] = Field(default_factory=set)

    # Payments
    cryptopay_api_token: str = "CHANGE_ME"
    cryptopay_api_base: str = "https://pay.crypt.bot/api"
    cryptopay_webhook_enabled: bool = True

    # Referral / rev-share
    referral_rate_standard: float = 0.20
    referral_rate_blogger: float = 0.30

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> object:
        """Accept a comma-separated string from the env (e.g. "111,222")."""
        if isinstance(v, str):
            return {int(part) for part in v.split(",") if part.strip()}
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
