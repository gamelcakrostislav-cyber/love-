"""Telegram bot entrypoint (aiogram 3.x).

Long-polls Telegram and dispatches to the client command router. Admin commands
are added in Phase 7.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import client
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

log = get_logger("bot")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(client.router)
    return dp


async def main() -> None:
    configure_logging()
    if not settings.bot_token or settings.bot_token == "CHANGE_ME":
        log.warning("BOT_TOKEN not set — bot idling (set it in .env to enable)")
        while True:
            await asyncio.sleep(3600)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()
    log.info("bot starting (long polling)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
