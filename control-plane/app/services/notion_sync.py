"""Notion CRM sync — mirror business data into auto-built, linked Notion DBs.

One-way, best-effort, idempotent. On each reconcile pass we:
  1. ensure the six linked Notion databases exist (create them under the parent
     page on first run, remembering their ids in the `notion_sync` table);
  2. push new/changed rows (Customers, Payments, Subscriptions, Referrals,
     Commissions, Flags) as Notion pages, skipping unchanged rows via a stored
     content hash, and linking child rows back to their Customer via relations.

Everything is guarded: disabled unless configured, a Redis lock prevents
overlapping runs, a per-run write budget bounds Notion API traffic, and every
network call is wrapped so one failure never aborts the pass (it retries next
tick). Nothing here ever raises into the worker.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.integrations import notion as n
from app.models.abuse_event import AbuseEvent
from app.models.api_key import ApiKey
from app.models.device import Device
from app.models.enums import ApiKeyStatus, DeviceStatus, SubscriptionStatus
from app.models.notion_sync import NotionSync
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.referral import Commission, Referral
from app.models.subscription import Subscription
from app.models.user import User

log = get_logger("notion")

_MAX_WRITES_PER_RUN = 60   # bound Notion API traffic per reconcile pass
_SCAN_LIMIT = 1000         # newest-N rows considered per entity type per pass
_LOCK_TTL = 600            # seconds; safety release if a run dies mid-flight

_DB_ORDER = ["customers", "payments", "subscriptions", "referrals", "commissions", "flags"]
_DB_TITLES = {
    "customers": "Customers",
    "payments": "Payments",
    "subscriptions": "Subscriptions",
    "referrals": "Referrals",
    "commissions": "Commissions",
    "flags": "Flags & Abuse",
}


def is_enabled() -> bool:
    return bool(
        settings.notion_sync_enabled
        and settings.notion_api_key
        and settings.notion_api_key != "CHANGE_ME"
        and settings.notion_parent_page_id
    )


def page_url(notion_id: str) -> str:
    return "https://www.notion.so/" + notion_id.replace("-", "")


# ─── Database schemas (property name -> Notion property schema) ───────────────
def db_schema(key: str, ids: dict[str, str]) -> dict:
    """Schema for database `key`; `ids` holds ids of already-created databases."""
    if key == "customers":
        return {
            "Customer": n.s_title(), "Telegram ID": n.s_number(), "Username": n.s_text(),
            "Language": n.s_select(), "Plan": n.s_select(), "Status": n.s_select(),
            "Expires": n.s_date(), "API Key": n.s_text(), "Devices": n.s_number(),
            "Risk": n.s_number(), "Blogger": n.s_checkbox(), "Referrals": n.s_number(),
            "Earnings": n.s_number("dollar"), "Joined": n.s_date(),
        }
    if key == "payments":
        return {
            "Invoice": n.s_title(), "Customer": n.s_relation(ids["customers"]),
            "Amount": n.s_number("dollar"), "Currency": n.s_select(),
            "Provider": n.s_select(), "Status": n.s_select(), "Payer": n.s_text(),
            "Created": n.s_date(),
        }
    if key == "subscriptions":
        return {
            "Subscription": n.s_title(), "Customer": n.s_relation(ids["customers"]),
            "Plan": n.s_select(), "Status": n.s_select(), "Started": n.s_date(),
            "Expires": n.s_date(),
        }
    if key == "referrals":
        return {
            "Referral": n.s_title(), "Referrer": n.s_relation(ids["customers"]),
            "Referred": n.s_relation(ids["customers"]), "Type": n.s_select(),
            "Rate": n.s_number("percent"), "Status": n.s_select(),
            "Created": n.s_date(), "Qualified": n.s_date(),
        }
    if key == "commissions":
        return {
            "Commission": n.s_title(), "Referrer": n.s_relation(ids["customers"]),
            "Amount": n.s_number("dollar"), "Currency": n.s_select(),
            "Rate": n.s_number("percent"), "Status": n.s_select(),
            "Payment": n.s_relation(ids["payments"]), "Created": n.s_date(),
        }
    if key == "flags":
        return {
            "Event": n.s_title(), "Customer": n.s_relation(ids["customers"]),
            "Type": n.s_select(), "Detail": n.s_text(), "Created": n.s_date(),
        }
    raise KeyError(key)


# ─── Entity -> Notion page property VALUES (pure; testable with stand-ins) ────
def customer_props(u, *, plan, status, expires_at, key_prefix, devices, referrals, earnings) -> dict:
    handle = f"@{u.username}" if u.username else f"tg:{u.telegram_id}"
    return {
        "Customer": n.title(handle),
        "Telegram ID": n.number(u.telegram_id),
        "Username": n.text(u.username),
        "Language": n.select(u.language),
        "Plan": n.select(plan),
        "Status": n.select(status),
        "Expires": n.date(expires_at),
        "API Key": n.text(f"{key_prefix}…" if key_prefix else None),
        "Devices": n.number(devices),
        "Risk": n.number(u.risk_score),
        "Blogger": n.checkbox(u.is_blogger),
        "Referrals": n.number(referrals),
        "Earnings": n.number(earnings),
        "Joined": n.date(u.created_at),
    }


def payment_props(p, *, customer_page) -> dict:
    return {
        "Invoice": n.title(p.external_id),
        "Customer": n.relation(customer_page),
        "Amount": n.number(p.amount),
        "Currency": n.select(p.currency),
        "Provider": n.select(p.provider),
        "Status": n.select(p.status),
        "Payer": n.text(p.payer_fingerprint),
        "Created": n.date(p.created_at),
    }


def subscription_props(s, *, customer_page, plan_name) -> dict:
    return {
        "Subscription": n.title(f"{plan_name or 'sub'} #{s.id}"),
        "Customer": n.relation(customer_page),
        "Plan": n.select(plan_name),
        "Status": n.select(s.status),
        "Started": n.date(s.started_at),
        "Expires": n.date(s.expires_at),
    }


def referral_props(r, *, referrer_page, referred_page) -> dict:
    return {
        "Referral": n.title(f"Referral #{r.id}"),
        "Referrer": n.relation(referrer_page),
        "Referred": n.relation(referred_page),
        "Type": n.select(r.referrer_type),
        "Rate": n.number(r.rate),
        "Status": n.select(r.status),
        "Created": n.date(r.created_at),
        "Qualified": n.date(r.qualified_at),
    }


def commission_props(c, *, referrer_page, payment_page) -> dict:
    return {
        "Commission": n.title(f"Commission #{c.id}"),
        "Referrer": n.relation(referrer_page),
        "Amount": n.number(c.amount),
        "Currency": n.select(c.currency),
        "Rate": n.number(c.rate),
        "Status": n.select(c.status),
        "Payment": n.relation(payment_page),
        "Created": n.date(c.created_at),
    }


def abuse_props(e, *, customer_page) -> dict:
    return {
        "Event": n.title(f"{e.type} #{e.id}"),
        "Customer": n.relation(customer_page),
        "Type": n.select(e.type),
        "Detail": n.text(e.detail),
        "Created": n.date(e.created_at),
    }


def content_hash(props: dict) -> str:
    return hashlib.sha256(json.dumps(props, sort_keys=True, default=str).encode()).hexdigest()


# ─── Upsert + reconcile ──────────────────────────────────────────────────────
class _Budget:
    def __init__(self, limit: int) -> None:
        self.left = limit


async def _upsert(db, mappings, budget, *, kind, ref, db_id, props) -> str | None:
    """Create/update one Notion page idempotently; return its page id (or None)."""
    h = content_hash(props)
    row = mappings.get((kind, ref))
    if row is None:
        if budget.left <= 0:
            return None  # defer creation to a later pass
        try:
            page_id = await n.create_page(db_id, props)
        except Exception as exc:  # noqa: BLE001 - never abort the pass on one row
            log.warning("notion create %s/%s failed: %s", kind, ref, exc)
            return None
        row = NotionSync(kind=kind, ref=ref, notion_id=page_id, content_hash=h)
        db.add(row)
        # Persist the mapping the instant the remote page exists. Notion's
        # page-create has no idempotency key, so a crash between create and a
        # batched commit would re-create the page next run. A commit per *create*
        # (bounded by the write budget) closes that window. Updates are
        # idempotent on page_id, so they ride the per-phase commit.
        await db.commit()
        mappings[(kind, ref)] = row
        budget.left -= 1
        return page_id
    if row.content_hash != h:
        if budget.left <= 0:
            return row.notion_id
        try:
            await n.update_page(row.notion_id, props)
        except Exception as exc:  # noqa: BLE001
            log.warning("notion update %s/%s failed: %s", kind, ref, exc)
            return row.notion_id
        row.content_hash = h
        budget.left -= 1
    return row.notion_id


async def _ensure_databases(db, mappings) -> dict[str, str] | None:
    ids: dict[str, str] = {}
    created = False
    for key in _DB_ORDER:
        row = mappings.get(("database", key))
        if row is not None:
            ids[key] = row.notion_id
            continue
        try:
            db_id = await n.create_database(
                settings.notion_parent_page_id, _DB_TITLES[key], db_schema(key, ids)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("notion create database %s failed: %s", key, exc)
            return None
        row = NotionSync(kind="database", ref=key, notion_id=db_id, content_hash=None)
        db.add(row)
        await db.commit()  # durable before the NEXT create_database/page references it
        mappings[("database", key)] = row
        ids[key] = db_id
        created = True
    if created:
        log.info("notion: ensured %d databases", len(ids))
    return ids


async def _load_mappings(db) -> dict[tuple[str, str], NotionSync]:
    rows = list(await db.scalars(select(NotionSync)))
    return {(r.kind, r.ref): r for r in rows}


async def _customer_aggregates(db, now: datetime):
    """Per-user derived data, computed in a handful of grouped queries (no N+1)."""
    active: dict[int, tuple[str, datetime]] = {}
    rows = await db.execute(
        select(Subscription.user_id, Plan.name, Subscription.expires_at)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at > now)
        .order_by(Subscription.expires_at.desc())
    )
    for user_id, plan_name, expires_at in rows:
        active.setdefault(user_id, (plan_name, expires_at))

    prefixes: dict[int, str] = {}
    rows = await db.execute(
        select(ApiKey.user_id, ApiKey.prefix)
        .where(ApiKey.status == ApiKeyStatus.ACTIVE)
        .order_by(ApiKey.created_at.desc())
    )
    for user_id, prefix in rows:
        prefixes.setdefault(user_id, prefix)

    devices = dict((await db.execute(
        select(ApiKey.user_id, func.count(Device.id))
        .join(Device, Device.key_id == ApiKey.id)
        .where(Device.status != DeviceStatus.REMOVED)
        .group_by(ApiKey.user_id)
    )).all())

    referrals = dict((await db.execute(
        select(Referral.referrer_user_id, func.count())
        .group_by(Referral.referrer_user_id)
    )).all())

    earnings = dict((await db.execute(
        select(Commission.referrer_user_id, func.coalesce(func.sum(Commission.amount), 0))
        .group_by(Commission.referrer_user_id)
    )).all())

    return active, prefixes, devices, referrals, earnings


async def reconcile(db: AsyncSession) -> int | None:
    """Push new/changed rows to Notion.

    Returns the number of pages written, or None if another run holds the lock
    (so callers can tell "already running" apart from "ran, nothing to do").
    """
    if not is_enabled():
        return 0

    got = await redis_client.set(redis_keys.sync_lock("notion"), "1", nx=True, ex=_LOCK_TTL)
    if not got:
        return None
    try:
        now = datetime.now(UTC)
        mappings = await _load_mappings(db)
        ids = await _ensure_databases(db, mappings)
        if ids is None:
            return 0
        budget = _Budget(_MAX_WRITES_PER_RUN)

        # 1) Customers first — they own the relations every other row links to.
        active, prefixes, dev_counts, ref_counts, earn = await _customer_aggregates(db, now)
        user_pages: dict[int, str] = {}
        users = list(await db.scalars(select(User).order_by(User.id)))
        for u in users:
            plan_name, expires_at = active.get(u.id, (None, None))
            props = customer_props(
                u, plan=plan_name or "none", status="active" if plan_name else "inactive",
                expires_at=expires_at, key_prefix=prefixes.get(u.id),
                devices=dev_counts.get(u.id, 0), referrals=ref_counts.get(u.id, 0),
                earnings=earn.get(u.id, 0),
            )
            pid = await _upsert(db, mappings, budget, kind="customer", ref=str(u.id),
                                db_id=ids["customers"], props=props)
            if pid:
                user_pages[u.id] = pid
        await db.commit()

        plan_names = dict((await db.execute(select(Plan.id, Plan.name))).all())

        # Child rows carry a relation to their Customer. If that customer hasn't
        # been synced yet (deferred earlier by the write budget, or just-created
        # concurrently), we *skip* the child this pass rather than writing an
        # empty relation — it syncs on a later pass once the customer exists.
        # This keeps relations correct instead of permanently empty.

        # 2) Payments (build payment page map for commissions).
        payment_pages: dict[int, str] = {}
        payments = list(await db.scalars(
            select(Payment).order_by(Payment.id.desc()).limit(_SCAN_LIMIT)))
        for p in payments:
            cp = user_pages.get(p.user_id)
            if cp is None:
                continue
            props = payment_props(p, customer_page=cp)
            pid = await _upsert(db, mappings, budget, kind="payment", ref=str(p.id),
                                db_id=ids["payments"], props=props)
            if pid:
                payment_pages[p.id] = pid
        await db.commit()

        # 3) Subscriptions.
        subs = list(await db.scalars(
            select(Subscription).order_by(Subscription.id.desc()).limit(_SCAN_LIMIT)))
        for s in subs:
            cp = user_pages.get(s.user_id)
            if cp is None:
                continue
            props = subscription_props(s, customer_page=cp, plan_name=plan_names.get(s.plan_id))
            await _upsert(db, mappings, budget, kind="subscription", ref=str(s.id),
                          db_id=ids["subscriptions"], props=props)
        await db.commit()

        # 4) Referrals (need both endpoints' customer pages).
        refs = list(await db.scalars(
            select(Referral).order_by(Referral.id.desc()).limit(_SCAN_LIMIT)))
        for r in refs:
            rp = user_pages.get(r.referrer_user_id)
            rdp = user_pages.get(r.referred_user_id)
            if rp is None or rdp is None:
                continue
            props = referral_props(r, referrer_page=rp, referred_page=rdp)
            await _upsert(db, mappings, budget, kind="referral", ref=str(r.id),
                          db_id=ids["referrals"], props=props)
        await db.commit()

        # 5) Commissions (anchored on the referrer customer; payment link is
        #    secondary and filled in when that payment has been synced).
        coms = list(await db.scalars(
            select(Commission).order_by(Commission.id.desc()).limit(_SCAN_LIMIT)))
        for c in coms:
            rp = user_pages.get(c.referrer_user_id)
            if rp is None:
                continue
            props = commission_props(c, referrer_page=rp,
                                     payment_page=payment_pages.get(c.payment_id))
            await _upsert(db, mappings, budget, kind="commission", ref=str(c.id),
                          db_id=ids["commissions"], props=props)
        await db.commit()

        # 6) Flags / abuse events (user_id may legitimately be NULL -> no customer).
        evs = list(await db.scalars(
            select(AbuseEvent).order_by(AbuseEvent.id.desc()).limit(_SCAN_LIMIT)))
        for e in evs:
            cp = None
            if e.user_id is not None:
                cp = user_pages.get(e.user_id)
                if cp is None:
                    continue  # has a customer, just not synced yet — defer
            props = abuse_props(e, customer_page=cp)
            await _upsert(db, mappings, budget, kind="abuse", ref=str(e.id),
                          db_id=ids["flags"], props=props)
        await db.commit()

        return _MAX_WRITES_PER_RUN - budget.left
    finally:
        await redis_client.delete(redis_keys.sync_lock("notion"))


async def status(db: AsyncSession) -> dict:
    """Lightweight status for the /notion admin command (no Notion API calls)."""
    mappings = await _load_mappings(db)
    dbs = {k: r.notion_id for (kind, k), r in mappings.items() if kind == "database"}
    synced = sum(1 for (kind, _) in mappings if kind not in ("database",))
    return {
        "enabled": is_enabled(),
        "configured": bool(settings.notion_api_key != "CHANGE_ME" and settings.notion_parent_page_id),
        "databases": dbs,
        "synced_pages": synced,
    }
