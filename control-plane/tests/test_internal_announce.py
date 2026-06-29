"""POST /internal/announce — shared-secret auth + posting into the group."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from app.core.config import settings
from app.gateway.main import create_app
from app.services import club


@pytest.fixture
def client():
    return httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


async def test_disabled_when_no_token_configured(client):
    # Default INTERNAL_API_TOKEN is "" → endpoint is off and fails closed.
    async with client:
        r = await client.post("/internal/announce", json={"text": "hi"})
    assert r.status_code == 503
    assert r.json()["detail"] == "internal_api_disabled"


async def test_rejects_missing_bearer(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_token", "s3cret")
    async with client:
        r = await client.post("/internal/announce", json={"text": "hi"})
    assert r.status_code == 401


async def test_rejects_bad_token(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_token", "s3cret")
    async with client:
        r = await client.post(
            "/internal/announce", json={"text": "hi"},
            headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


async def test_503_when_group_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_token", "s3cret")
    monkeypatch.setattr(club, "is_enabled", lambda: False)
    async with client:
        r = await client.post(
            "/internal/announce", json={"text": "hi"},
            headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 503
    assert r.json()["detail"] == "subscriber_group_not_configured"


async def test_rejects_empty_text(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_token", "s3cret")
    monkeypatch.setattr(club, "is_enabled", lambda: True)
    async with client:
        r = await client.post(
            "/internal/announce", json={"text": ""},
            headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 422  # pydantic min_length=1


async def test_posts_with_valid_token(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_token", "s3cret")
    monkeypatch.setattr(club, "is_enabled", lambda: True)
    calls: dict = {}

    async def fake_announce(text, *, topic_id=None, pin=False):
        calls.update(text=text, topic_id=topic_id, pin=pin)
        return 555

    monkeypatch.setattr(club, "announce", fake_announce)
    async with client:
        r = await client.post(
            "/internal/announce",
            json={"text": "New signal 📈", "topic_id": 9, "pin": True},
            headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "message_id": 555}
    assert calls == {"text": "New signal 📈", "topic_id": 9, "pin": True}
