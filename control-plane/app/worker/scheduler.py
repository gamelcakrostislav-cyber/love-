"""Background worker (APScheduler).

Every minute: expire subscriptions past their deadline (disabling keys and
killing their Redis sessions), then reap stale DB session rows. This is what
makes expiry server-enforced — the client can never self-extend.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.db import SessionFactory
from app.core.logging import configure_logging, get_logger
from app.services import notion_sync, revocation

log = get_logger("worker")


async def tick() -> None:
    async with SessionFactory() as db:
        expired = await revocation.expire_due(db)
        reaped = await revocation.reap_sessions(db)
        await db.commit()
    if expired or reaped:
        log.info("expiry sweep: %d subscriptions expired, %d sessions reaped", expired, reaped)


async def notion_tick() -> None:
    try:
        async with SessionFactory() as db:
            written = await notion_sync.reconcile(db)
        if written:
            log.info("notion sync: %d pages upserted", written)
    except Exception as exc:  # noqa: BLE001 - sync must never crash the worker
        log.warning("notion sync failed: %s", exc)


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
    if notion_sync.is_enabled():
        scheduler.add_job(
            notion_tick,
            trigger="interval",
            minutes=max(1, settings.notion_reconcile_minutes),
            next_run_time=datetime.now(),  # do an initial sync on boot
            max_instances=1,
            coalesce=True,
        )
        log.info("notion sync enabled — reconcile every %d min", settings.notion_reconcile_minutes)

    scheduler.start()
    log.info("worker started — expiry sweep every minute")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
