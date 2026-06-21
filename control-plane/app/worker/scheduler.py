"""Background worker entrypoint (placeholder).

Phase 7 adds the APScheduler jobs: expire subscriptions past `expires_at`,
disable their keys, and reap their Redis sessions every minute.
"""

from __future__ import annotations

import asyncio

from app.core.logging import configure_logging, get_logger

log = get_logger("worker")


async def main() -> None:
    configure_logging()
    log.info("worker placeholder running — schedules land in Phase 7")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
