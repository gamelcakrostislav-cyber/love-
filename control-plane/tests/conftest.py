"""Pytest fixtures.

Tests run against a real Postgres + Redis (the compose services), since the
models use Postgres-specific types (JSONB/BigInteger) and the licensing logic is
inseparable from Redis. Env defaults below point at a dedicated test database and
Redis db index; override via env vars in CI.

The test DB is created if missing, the schema is built once from the models, and
every test starts from a truncated DB + flushed Redis for isolation. A
session-scoped event loop + NullPool engine avoid the asyncpg "attached to a
different loop" pitfalls.
"""

from __future__ import annotations

import os

# Must be set before any app import so the settings singleton picks them up.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://control:control@localhost:5432/control_plane_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("REQUEST_SIGNING_REQUIRED", "false")
os.environ.setdefault("CRYPTOPAY_API_TOKEN", "test-token")
os.environ.setdefault("BOT_TOKEN", "CHANGE_ME")

import asyncpg  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.models  # noqa: E402,F401 — imports all models, populates metadata
from app.core.config import settings  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.redis import redis_client  # noqa: E402

test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)


async def _ensure_database() -> None:
    url = make_url(settings.database_url)
    admin = await asyncpg.connect(
        user=url.username, password=url.password,
        host=url.host, port=url.port, database="postgres",
    )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", url.database)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await admin.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    await _ensure_database()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await test_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    """Truncate all tables and flush Redis before each test."""
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await redis_client.flushdb()
    yield


@pytest_asyncio.fixture
async def db():
    async with TestSession() as session:
        yield session
