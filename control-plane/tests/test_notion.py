"""Notion CRM sync — pure logic (offline): property/schema builders, the
props<->schema contract, content hashing and the enabled/url guards.

No network and no DB: ORM rows are stand-ins (the mapping functions only read
attributes). Skips cleanly if optional deps aren't installed."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")

from app.core import redis_keys  # noqa: E402
from app.integrations import notion as n  # noqa: E402
from app.services import notion_sync as ns  # noqa: E402

DT = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def test_value_builders():
    assert n.title("hi") == {"title": [{"text": {"content": "hi"}}]}
    assert n.text(None) == {"rich_text": []}
    assert n.number(Decimal("49.00")) == {"number": 49.0}
    assert n.number(None) == {"number": None}
    assert n.select("monthly") == {"select": {"name": "monthly"}}
    assert n.select(None) == {"select": None}
    assert n.select("a,b")["select"]["name"] == "a b"  # commas not allowed in Notion select
    assert n.date(DT) == {"date": {"start": DT.isoformat()}}
    assert n.date(None) == {"date": None}
    assert n.checkbox(1) == {"checkbox": True}
    assert n.relation("p1", None, "p2") == {"relation": [{"id": "p1"}, {"id": "p2"}]}
    assert n.relation(None) == {"relation": []}


def test_schema_builders():
    assert n.s_title() == {"title": {}}
    assert n.s_number("dollar") == {"number": {"format": "dollar"}}
    assert n.s_relation("db1") == {"relation": {"database_id": "db1", "single_property": {}}}


def test_each_database_has_exactly_one_title():
    ids = {"customers": "C", "payments": "P"}
    for key in ns._DB_ORDER:
        sch = ns.db_schema(key, ids)
        titles = [k for k, v in sch.items() if v == {"title": {}}]
        assert len(titles) == 1, (key, titles)


def _rows():
    u = SimpleNamespace(id=1, telegram_id=42, username="alice", language="en",
                        risk_score=3, is_blogger=True, created_at=DT)
    p = SimpleNamespace(id=7, external_id="inv_1", amount=Decimal("49.00"), currency="USD",
                        provider="cryptopay", status="paid", payer_fingerprint=None, created_at=DT)
    s = SimpleNamespace(id=3, status="active", started_at=DT, expires_at=DT)
    r = SimpleNamespace(id=4, referrer_type="blogger", rate=Decimal("0.300"),
                        status="qualified", created_at=DT, qualified_at=None)
    c = SimpleNamespace(id=5, amount=Decimal("9.80"), currency="USD", rate=Decimal("0.200"),
                        status="payable", created_at=DT)
    e = SimpleNamespace(id=6, type="impossible_travel", detail="x->y", created_at=DT)
    return u, p, s, r, c, e


def test_props_keys_match_their_schema_exactly():
    """Guards against schema/props drift — a page prop with no schema column is dropped by Notion."""
    ids = {"customers": "C", "payments": "P"}
    schema_keys = {k: set(ns.db_schema(k, ids)) for k in ns._DB_ORDER}
    u, p, s, r, c, e = _rows()

    cust = ns.customer_props(u, plan="monthly", status="active", expires_at=DT,
                             key_prefix="ab12", devices=2, referrals=5, earnings=Decimal("12.5"))
    assert set(cust) == schema_keys["customers"]
    assert ns.payment_props(p, customer_page="cp").keys() == schema_keys["payments"]
    assert set(ns.subscription_props(s, customer_page="cp", plan_name="yearly")) == schema_keys["subscriptions"]
    assert set(ns.referral_props(r, referrer_page="a", referred_page="b")) == schema_keys["referrals"]
    assert set(ns.commission_props(c, referrer_page="a", payment_page="p")) == schema_keys["commissions"]
    assert set(ns.abuse_props(e, customer_page=None)) == schema_keys["flags"]


def test_relation_values():
    _, p, *_ = _rows()
    assert ns.payment_props(p, customer_page="cp")["Customer"] == {"relation": [{"id": "cp"}]}
    *_, e = _rows()
    assert ns.abuse_props(e, customer_page=None)["Customer"] == {"relation": []}


def test_content_hash_is_deterministic_and_change_sensitive():
    u, *_ = _rows()
    base = dict(plan="monthly", status="active", expires_at=DT, key_prefix="ab12",
                devices=2, referrals=5, earnings=Decimal("12.5"))
    h1 = ns.content_hash(ns.customer_props(u, **base))
    h2 = ns.content_hash(ns.customer_props(u, **base))
    h3 = ns.content_hash(ns.customer_props(u, **{**base, "plan": "yearly"}))
    assert h1 == h2 and h1 != h3 and len(h1) == 64


def test_guards():
    assert ns.page_url("abc-def-12") == "https://www.notion.so/abcdef12"
    assert redis_keys.sync_lock("notion") == "lock:sync:notion"
