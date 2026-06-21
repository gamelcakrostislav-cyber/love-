"""FastAPI gateway application.

Phase 1 wires only the app factory and a health-check that proves Postgres and
Redis connectivity. Licensing, protected, and webhook routers land in later
phases.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.db import engine
from app.core.logging import configure_logging, get_logger
from app.core.redis import ping as redis_ping
from app.gateway.routers import auth, protected
from app.services.errors import LicensingError

log = get_logger("gateway")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    log.info("gateway starting")
    yield
    await engine.dispose()
    log.info("gateway stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Control Plane Gateway", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(LicensingError)
    async def _licensing_error_handler(_: Request, exc: LicensingError) -> JSONResponse:
        # Map typed entitlement failures to stable codes + HTTP statuses.
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": exc.code, "detail": exc.message},
        )

    app.include_router(auth.router)
    app.include_router(protected.router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict:
        checks = {"postgres": False, "redis": False}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = True
        except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
            log.warning("postgres health check failed: %s", exc)
        try:
            checks["redis"] = await redis_ping()
        except Exception as exc:  # noqa: BLE001
            log.warning("redis health check failed: %s", exc)

        status = "ok" if all(checks.values()) else "degraded"
        return {"status": status, "checks": checks}

    return app


app = create_app()
