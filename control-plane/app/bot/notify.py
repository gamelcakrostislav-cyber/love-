"""Fire-and-forget DM helper for out-of-band notifications (e.g. the webhook
DM-ing a freshly issued key). Uses a transient Bot so the gateway process can
message users without running the dispatcher."""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("notify")


async def send_message(telegram_id: int, text: str) -> None:
    if not settings.bot_token or settings.bot_token == "CHANGE_ME":
        log.warning("BOT_TOKEN unset — skipping DM to %s", telegram_id)
        return
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await bot.send_message(telegram_id, text)
    except Exception as exc:  # noqa: BLE001 - never let a DM failure break the webhook
        log.warning("failed DM to %s: %s", telegram_id, exc)
    finally:
        await bot.session.close()
