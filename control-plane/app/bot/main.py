"""Telegram bot entrypoint (placeholder).

Phase 1 keeps the process alive so the compose stack is healthy. The aiogram
dispatcher, client commands, and admin commands are implemented in Phase 5/7.
"""

from __future__ import annotations

import asyncio

from app.core.logging import configure_logging, get_logger

log = get_logger("bot")


async def main() -> None:
    configure_logging()
    log.info("bot placeholder running — handlers land in Phase 5")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
