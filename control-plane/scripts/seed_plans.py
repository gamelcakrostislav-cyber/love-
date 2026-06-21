"""Seed (idempotently) the plan catalog.

Run after migrations:  python -m scripts.seed_plans

Plans:
  trial    free  /  7d   — only opportunities with profitability <= 2%
  monthly  $49   / 30d   — all opportunities
  yearly   $479  / 365d  — all opportunities
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.core.db import SessionFactory
from app.core.logging import configure_logging, get_logger
from app.models.plan import Plan

log = get_logger("seed")

PLANS: list[dict] = [
    {
        "name": "trial",
        "price": Decimal("0.00"),
        "currency": "USD",
        "duration_days": 7,
        "rate_limit_per_min": 10,
        "max_devices": 1,
        "max_concurrent_sessions": 1,
        "is_trial": True,
        "max_profitability": Decimal("0.0200"),  # trial sees only the <=2% tier
        "is_active": True,
    },
    {
        "name": "monthly",
        "price": Decimal("49.00"),
        "currency": "USD",
        "duration_days": 30,
        "rate_limit_per_min": 120,
        "max_devices": 2,
        "max_concurrent_sessions": 2,
        "is_trial": False,
        "max_profitability": None,  # all opportunities
        "is_active": True,
    },
    {
        "name": "yearly",
        "price": Decimal("479.00"),
        "currency": "USD",
        "duration_days": 365,
        "rate_limit_per_min": 120,
        "max_devices": 3,
        "max_concurrent_sessions": 2,
        "is_trial": False,
        "max_profitability": None,
        "is_active": True,
    },
]


async def seed() -> None:
    configure_logging()
    async with SessionFactory() as session:
        for spec in PLANS:
            existing = await session.scalar(select(Plan).where(Plan.name == spec["name"]))
            if existing is None:
                session.add(Plan(**spec))
                log.info("seeding plan %s", spec["name"])
            else:
                # Keep catalog in sync with the source of truth on re-run.
                for field, value in spec.items():
                    setattr(existing, field, value)
                log.info("updating plan %s", spec["name"])
        await session.commit()
    log.info("plan seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
