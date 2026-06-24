"""Application settings, loaded from environment / .env via pydantic-settings.

Every secret comes from the environment — nothing sensitive is hard-coded or
committed. Import the singleton `settings` everywhere; it is parsed once.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # NoDecode stops pydantic-settings from JSON-decoding the env value before our
    # validator runs, so a bare "1966832731" or a "111,222" list both work.
    admin_ids: Annotated[set[int], NoDecode] = Field(default_factory=set)

    # Payments
    cryptopay_api_token: str = "CHANGE_ME"
    cryptopay_api_base: str = "https://pay.crypt.bot/api"
    cryptopay_webhook_enabled: bool = True

    # Referral / rev-share
    referral_rate_standard: float = 0.20
    referral_rate_blogger: float = 0.30

    # AI support agent — any OpenAI-compatible provider (default: free Groq)
    support_ai_enabled: bool = True
    support_provider: str = "groq"
    support_api_key: str = "CHANGE_ME"
    support_model: str = "llama-3.3-70b-versatile"
    support_base_url: str = "https://api.groq.com/openai/v1"
    support_history_turns: int = 10  # how many prior turns to send as context

    # Notion sync — mirror business data into an auto-built Notion CRM/dashboard.
    # Disabled until NOTION_API_KEY is set (and != CHANGE_ME) and a parent page id
    # is provided. The worker reconciles every notion_reconcile_minutes.
    notion_sync_enabled: bool = False
    notion_api_key: str = "CHANGE_ME"
    notion_parent_page_id: str = ""
    notion_api_base: str = "https://api.notion.com/v1"
    notion_version: str = "2022-06-28"
    notion_reconcile_minutes: int = 3
    # Two-way: apply grant/revoke/blogger actions set from a Notion field, routed
    # through the same server-side path as admin commands (never bypasses access).
    notion_allow_actions: bool = True

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> object:
        """Parse ADMIN_IDS forgivingly.

        Accepts a bare id ("123"), a comma list ("111,222"), a bracketed/JSON-ish
        form ("[111, 222]"), an int, or an existing iterable. Empty -> empty set.
        """
        if v is None or v == "":
            return set()
        if isinstance(v, int):
            return {v}
        if isinstance(v, (set, list, tuple)):
            return {int(x) for x in v}
        if isinstance(v, str):
            cleaned = v.strip().strip("[]")
            return {int(part.strip().strip("'\"")) for part in cleaned.split(",") if part.strip()}
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
