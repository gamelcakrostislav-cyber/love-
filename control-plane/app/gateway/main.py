"""FastAPI gateway application.

Phase 1 wires only the app factory and a health-check that proves Postgres and
Redis connectivity. Licensing, protected, and webhook routers land in later
phases.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.db import engine
from app.core.logging import configure_logging, get_logger
from app.core.redis import ping as redis_ping
from app.gateway.routers import auth, internal, protected, webapp, webhooks
from app.services.errors import LicensingError

log = get_logger("gateway")
_WEBAPP_STATIC = Path(__file__).resolve().parent.parent / "webapp" / "static"


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

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        # Safe baseline. NOTE: no X-Frame-Options/frame-ancestors DENY — a Mini
        # App is legitimately framed by Telegram. Tighten CSP in deploy/Caddyfile.
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    app.include_router(auth.router)
    app.include_router(protected.router)
    app.include_router(webhooks.router)
    app.include_router(webapp.router)
    app.include_router(internal.router)
    # Serve the Mini App static bundle at /app (HTTPS required by Telegram).
    # check_dir=False so a missing bundle degrades to 404s instead of crashing.
    app.mount("/app", StaticFiles(directory=str(_WEBAPP_STATIC), html=True, check_dir=False),
              name="webapp")

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
