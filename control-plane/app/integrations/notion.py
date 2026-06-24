"""Minimal Notion API client (v2022-06-28) over httpx — no SDK required.

Mirrors the lazy/cached client style of app/services/support.py. Exposes just
what the CRM sync needs: create a database, create a page, update a page; plus
pure helpers that build Notion property *values* (for pages) and property
*schemas* (for databases). The pure helpers are unit-tested offline.

A small async throttle keeps us under Notion's ~3 requests/second limit. All
network methods raise on HTTP error; callers (app/services/notion_sync.py) wrap
each operation so one bad row never aborts a whole reconcile pass.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from decimal import Decimal

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("notion")

# Notion allows ~3 requests/second on average; keep a safe minimum gap.
_MIN_INTERVAL = 0.34
_throttle_lock = asyncio.Lock()
_last_call = 0.0

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.notion_api_base.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.notion_api_key}",
                "Notion-Version": settings.notion_version,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    return _client


async def _request(method: str, path: str, payload: dict | None = None) -> dict:
    global _last_call
    async with _throttle_lock:
        gap = time.monotonic() - _last_call
        if gap < _MIN_INTERVAL:
            await asyncio.sleep(_MIN_INTERVAL - gap)
        _last_call = time.monotonic()
    resp = await _get_client().request(method, path, json=payload)
    resp.raise_for_status()
    return resp.json()


async def create_database(parent_page_id: str, title: str, properties: dict) -> str:
    """Create a database under a parent page; return its id."""
    data = await _request("POST", "/databases", {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    })
    return data["id"]


async def create_page(database_id: str, properties: dict) -> str:
    """Create a page (row) in a database; return its id."""
    data = await _request("POST", "/pages", {
        "parent": {"database_id": database_id},
        "properties": properties,
    })
    return data["id"]


async def update_page(page_id: str, properties: dict) -> None:
    """Patch an existing page's properties."""
    await _request("PATCH", f"/pages/{page_id}", {"properties": properties})


# ─── Pure property-VALUE builders (for page create/update) ───────────────────
def _truncate(text: str, limit: int = 1900) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _select_name(name: str) -> str:
    # Notion select option names may not contain commas; cap length at 100.
    return _truncate(str(name).replace(",", " "), 100)


def title(text: str) -> dict:
    return {"title": [{"text": {"content": _truncate(text or "—")}}]}


def text(value: str | None) -> dict:
    if not value:
        return {"rich_text": []}
    return {"rich_text": [{"text": {"content": _truncate(value)}}]}


def number(value: int | float | Decimal | None) -> dict:
    return {"number": float(value) if value is not None else None}


def select(name: str | None) -> dict:
    return {"select": {"name": _select_name(name)} if name else None}


def date(value: datetime | None) -> dict:
    return {"date": {"start": value.isoformat()} if value else None}


def checkbox(value: bool) -> dict:
    return {"checkbox": bool(value)}


def relation(*page_ids: str | None) -> dict:
    return {"relation": [{"id": pid} for pid in page_ids if pid]}


# ─── Pure property-SCHEMA builders (for database creation) ───────────────────
def s_title() -> dict:
    return {"title": {}}


def s_text() -> dict:
    return {"rich_text": {}}


def s_number(fmt: str = "number") -> dict:
    return {"number": {"format": fmt}}


def s_select() -> dict:
    return {"select": {}}


def s_date() -> dict:
    return {"date": {}}


def s_checkbox() -> dict:
    return {"checkbox": {}}


def s_relation(database_id: str) -> dict:
    return {"relation": {"database_id": database_id, "single_property": {}}}
