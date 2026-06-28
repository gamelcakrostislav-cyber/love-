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


def test_verify_fails_closed_on_placeholder_token():
    # An unset/placeholder token would make the signing key a public constant —
    # verification must refuse even a "validly" signed payload.
    raw = sign_init_data("CHANGE_ME", {"id": 1})
    assert verify_init_data(raw, "CHANGE_ME") is None


# ─── Endpoints (DB + ASGI) ────────────────────────────────────────────────────
@pytest.fixture
def client():
    return httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


@pytest.fixture
def real_token(monkeypatch):
    """A non-placeholder bot token so initData auth passes; bot_username set so
    /me builds an invite link without a getMe network call."""
    monkeypatch.setattr(settings, "bot_token", "123456:TESTTOKEN")
    monkeypatch.setattr(settings, "bot_username", "testbot")
    return settings.bot_token


async def test_me_requires_init_data(client):
    async with client:
        r = await client.get("/webapp/api/me")
        assert r.status_code == 401


async def test_me_returns_subscription_and_referrals(db, client, real_token):
    plan = await make_plan(db, name="monthly", price="49.00")
    user = await make_user(db, telegram_id=900100, username="ceo")
    await make_subscription(db, user=user, plan=plan, days_left=20)
    await db.commit()

    auth = "tma " + sign_init_data(real_token, {"id": 900100, "username": "ceo"})
    async with client:
        r = await client.get("/webapp/api/me", headers={"Authorization": auth})
    assert r.status_code == 200
    data = r.json()
    assert data["telegram_id"] == 900100
    assert data["subscription"]["plan"] == "monthly"
    assert data["referrals"]["rate_pct"] == 20
    assert data["referrals"]["invite_link"] == "https://t.me/testbot?start=900100"


async def test_me_rejects_forged_when_token_is_placeholder(db, client):
    # With the default CHANGE_ME token, even a "validly" signed payload is refused.
    await make_user(db, telegram_id=900150)
    await db.commit()
    auth = "tma " + sign_init_data(settings.bot_token, {"id": 900150})  # bot_token == CHANGE_ME
    async with client:
        r = await client.get("/webapp/api/me", headers={"Authorization": auth})
    assert r.status_code == 401


async def test_plans_endpoint_lists_methods(db, client, real_token):
    await make_plan(db, name="monthly", price="49.00")
    await db.commit()
    auth = "tma " + sign_init_data(real_token, {"id": 900200})
    async with client:
        r = await client.get("/webapp/api/plans", headers={"Authorization": auth})
    assert r.status_code == 200
    body = r.json()
    assert any(p["name"] == "monthly" for p in body["plans"])
    assert "crypto" in body["methods"] and "stars" in body["methods"]


async def test_buy_rejects_bad_method_and_unknown_plan(db, client, real_token):
    await make_plan(db, name="monthly", price="49.00")
    await db.commit()
    auth = "tma " + sign_init_data(real_token, {"id": 900300})
    async with client:
        bad_method = await client.post(
            "/webapp/api/buy", headers={"Authorization": auth},
            json={"plan": "monthly", "method": "bogus"})
        unknown_plan = await client.post(
            "/webapp/api/buy", headers={"Authorization": auth},
            json={"plan": "ghost", "method": "stars", "code": 123})  # non-str code must not 500
    assert bad_method.status_code == 400
    assert unknown_plan.status_code == 400
