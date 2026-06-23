"""Human-handoff state for support.

When a user is handed off, their free-text messages are relayed to the admins
instead of going to the AI, and admins reply through the bot (`/reply`). State is
a simple Redis flag with a day-long TTL.
"""

from __future__ import annotations

from app.bot import notify
from app.core import redis_keys
from app.core.config import settings
from app.core.redis import redis_client

_TTL = 24 * 3600


async def enter(telegram_id: int) -> None:
    await redis_client.set(redis_keys.support_human(telegram_id), "1", ex=_TTL)


async def exit(telegram_id: int) -> None:  # noqa: A001 - intentional verb
    await redis_client.delete(redis_keys.support_human(telegram_id))


async def is_active(telegram_id: int) -> bool:
    return bool(await redis_client.exists(redis_keys.support_human(telegram_id)))


async def notify_admins(text: str) -> None:
    """DM every configured admin. Best-effort — failures are swallowed by notify."""
    for admin_id in settings.admin_ids:
        await notify.send_message(admin_id, text)
