"""Background worker (APScheduler).

Every minute: expire subscriptions past their deadline (disabling keys and
killing their Redis sessions), then reap stale DB session rows. This is what
makes expiry server-enforced — the client can never self-extend.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.db import SessionFactory
from app.core.logging import configure_logging, get_logger
from app.services import alerts, notion_sync, reminders, revocation

log = get_logger("worker")


async def tick() -> None:
    async with SessionFactory() as db:
        expired = await revocation.expire_due(db)
        reaped = await revocation.reap_sessions(db)
        await db.commit()
    if expired or reaped:
        log.info("expiry sweep: %d subscriptions expired, %d sessions reaped", expired, reaped)


async def reminder_tick() -> None:
    try:
        async with SessionFactory() as db:
            sent = await reminders.sweep(db)
            back = await reminders.winback_sweep(db)
        if sent or back:
            log.info("reminders: %d expiry, %d win-back", sent, back)
    except Exception as exc:  # noqa: BLE001 - reminders must never crash the worker
        log.warning("reminder sweep failed: %s", exc)


async def alert_tick() -> None:
    try:
        async with SessionFactory() as db:
            n = await alerts.abuse_sweep(db)
        if n:
            log.info("admin alerts: %d abuse events", n)
    except Exception as exc:  # noqa: BLE001 - alerts must never crash the worker
        log.warning("alert sweep failed: %s", exc)


async def notion_tick() -> None:
    try:
        # Apply any owner-set actions first, then mirror the (updated) state.
        async with SessionFactory() as db:
            applied = await notion_sync.apply_actions(db)
        if applied:
            log.info("notion actions: %d applied", applied)
        async with SessionFactory() as db:
            written = await notion_sync.reconcile(db)
        if written:  # None (lock held) and 0 (nothing to do) are both quiet
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
        next_run_time=datetime.now(UTC),  # run immediately on boot (UTC-aware)
        max_instances=1,
        coalesce=True,
    )
    if reminders.is_enabled() or reminders.winback_enabled():
        scheduler.add_job(
            reminder_tick,
            trigger="interval",
            minutes=max(5, settings.expiry_reminder_minutes),
            next_run_time=datetime.now(UTC),
            max_instances=1,
            coalesce=True,
        )
        log.info("reminders enabled — sweep every %d min", settings.expiry_reminder_minutes)

    if alerts.is_enabled():
        scheduler.add_job(
            alert_tick, trigger="interval", minutes=2,
            next_run_time=datetime.now(UTC), max_instances=1, coalesce=True,
        )
        log.info("admin abuse alerts enabled — sweep every 2 min")

    if notion_sync.is_enabled():
        scheduler.add_job(
            notion_tick,
            trigger="interval",
            minutes=max(1, settings.notion_reconcile_minutes),
            next_run_time=datetime.now(UTC),  # do an initial sync on boot (UTC-aware)
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
