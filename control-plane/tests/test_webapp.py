"""Mini App initData verification (security-critical) + the /webapp/api endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pytest
from httpx import ASGITransport

from app.core.config import settings
from app.gateway.main import create_app
from app.webapp.auth import verify_init_data
from tests.factories import make_plan, make_subscription, make_user


def sign_init_data(bot_token: str, user: dict, *, auth_date: int | None = None) -> str:
    """Build a valid Telegram initData query string for tests."""
    auth_date = auth_date if auth_date is not None else int(time.time())
    fields = {"auth_date": str(auth_date), "user": json.dumps(user, separators=(",", ":"))}
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


# ─── Verification (pure) ──────────────────────────────────────────────────────
def test_verify_accepts_a_valid_signature():
    raw = sign_init_data("token123", {"id": 42, "username": "neo"})
    info = verify_init_data(raw, "token123")
    assert info is not None and info.user_id == 42 and info.username == "neo"


def test_verify_rejects_wrong_token():
    raw = sign_init_data("token123", {"id": 42})
    assert verify_init_data(raw, "different-token") is None


def test_verify_rejects_tampered_field():
    raw = sign_init_data("token123", {"id": 42})
    tampered = raw.replace("auth_date=", "auth_date=9").rstrip()  # mutate a signed value
    assert verify_init_data(tampered, "token123") is None


def test_verify_rejects_forged_user():
    # Attacker swaps the user blob but keeps an old hash → must fail.
    raw = sign_init_data("token123", {"id": 42})
    forged = raw.replace("%22id%22%3A42", "%22id%22%3A999")
    assert verify_init_data(forged, "token123") is None


def test_verify_rejects_stale_init_data():
    raw = sign_init_data("token123", {"id": 42}, auth_date=int(time.time()) - 100_000)
    assert verify_init_data(raw, "token123", max_age=3600) is None
    # max_age=0 disables the freshness check
    assert verify_init_data(raw, "token123", max_age=0) is not None


def test_verify_rejects_missing_or_empty():
    assert verify_init_data("", "token123") is None
    assert verify_init_data("hash=abc", "token123") is None  # no signed fields
    assert verify_init_data(sign_init_data("t", {"id": 1}), "") is None


# ─── Endpoints (DB + ASGI) ────────────────────────────────────────────────────
@pytest.fixture
def client():
    return httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


async def test_me_requires_init_data(client):
    async with client:
        r = await client.get("/webapp/api/me")
        assert r.status_code == 401


async def test_me_returns_subscription_and_referrals(db, client):
    plan = await make_plan(db, name="monthly", price="49.00")
    user = await make_user(db, telegram_id=900100, username="ceo")
    await make_subscription(db, user=user, plan=plan, days_left=20)
    await db.commit()

    auth = "tma " + sign_init_data(settings.bot_token, {"id": 900100, "username": "ceo"})
    async with client:
        r = await client.get("/webapp/api/me", headers={"Authorization": auth})
    assert r.status_code == 200
    data = r.json()
    assert data["telegram_id"] == 900100
    assert data["subscription"]["plan"] == "monthly"
    assert data["referrals"]["rate_pct"] == 20


async def test_plans_endpoint_lists_methods(db, client):
    await make_plan(db, name="monthly", price="49.00")
    await db.commit()
    auth = "tma " + sign_init_data(settings.bot_token, {"id": 900200})
    async with client:
        r = await client.get("/webapp/api/plans", headers={"Authorization": auth})
    assert r.status_code == 200
    body = r.json()
    assert any(p["name"] == "monthly" for p in body["plans"])
    assert "crypto" in body["methods"] and "stars" in body["methods"]
