"""Background worker (APScheduler).

Every minute: expire subscriptions past their deadline (disabling keys and
killing their Redis sessions), then reap stale DB session rows. This is what
makes expiry server-enforced — the client can never self-extend.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.db import SessionFactory
from app.core.logging import configure_logging, get_logger
from app.services import revocation

log = get_logger("worker")


async def tick() -> None:
    async with SessionFactory() as db:
        expired = await revocation.expire_due(db)
        reaped = await revocation.reap_sessions(db)
        await db.commit()
    if expired or reaped:
        log.info("expiry sweep: %d subscriptions expired, %d sessions reaped", expired, reaped)


async def main() -> None:
    configure_logging()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        tick,
        trigger="interval",
        minutes=1,
        next_run_time=datetime.now(),  # run immediately on boot
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("worker started — expiry sweep every minute")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
