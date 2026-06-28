"""Thin Telegram Bot API client for the gateway / Mini App.

The bot process uses aiogram; the gateway occasionally needs two raw Bot API
calls — createInvoiceLink (so the Mini App can open a native invoice) and getMe
(to build invite links) — without pulling in the whole bot. Both fail closed
when the token is unset so local dev / CI never hit the network.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("tg-api")
_API = "https://api.telegram.org"
_me: dict[str, str] = {}


def _token_ok() -> bool:
    return bool(settings.bot_token) and settings.bot_token != "CHANGE_ME"


async def create_invoice_link(
    *, title: str, description: str, payload: str, currency: str,
    prices: list[dict], provider_token: str = "",
) -> str:
    """Create a shareable invoice link the Mini App opens via WebApp.openInvoice."""
    body: dict = {
        "title": title[:32], "description": description[:255], "payload": payload,
        "currency": currency, "prices": prices, "provider_token": provider_token,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{_API}/bot{settings.bot_token}/createInvoiceLink", json=body)
        resp.raise_for_status()
        data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"createInvoiceLink failed: {data}")
    return data["result"]


async def get_bot_username() -> str:
    """Bot @username. Prefers the configured value (no network); else a best-effort
    getMe, caching ONLY a successful result so a transient failure isn't sticky."""
    if settings.bot_username:
        return settings.bot_username
    if "username" in _me:
        return _me["username"]
    if not _token_ok():
        return ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_API}/bot{settings.bot_token}/getMe")
            resp.raise_for_status()
            data = resp.json()
        username = data.get("result", {}).get("username", "") or ""
    except Exception as exc:  # noqa: BLE001 - best-effort; never break a request
        log.warning("getMe failed: %s", exc)
        return ""
    if username:
        _me["username"] = username  # cache successes only
    return username
