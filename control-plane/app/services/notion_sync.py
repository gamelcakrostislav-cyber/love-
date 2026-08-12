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
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import notify
from app.core import redis_keys
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.integrations import notion as n
from app.models.abuse_event import AbuseEvent
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.enums import ApiKeyStatus, DeviceStatus, PaymentStatus, SubscriptionStatus
from app.models.notion_sync import NotionSync
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.referral import Commission, Referral
from app.models.subscription import Subscription
from app.models.user import User
from app.services import activation, revocation
from app.services.audit import record_audit

log = get_logger("notion")

_MAX_WRITES_PER_RUN = 60   # bound Notion API traffic per reconcile pass
_SCAN_LIMIT = 1000         # newest-N rows considered per entity type per pass
_LOCK_TTL = 600            # seconds; safety release if a run dies mid-flight
_SCHEMA_VERSION = "2"      # bump to re-patch existing databases (props/icons)

_DB_ORDER = ["customers", "payments", "subscriptions", "referrals", "commissions",
             "flags", "overview", "audit"]
_DB_TITLES = {
    "customers": "Customers",
    "payments": "Payments",
    "subscriptions": "Subscriptions",
    "referrals": "Referrals",
    "commissions": "Commissions",
    "flags": "Flags & Abuse",
    "overview": "Overview",
    "audit": "Audit Log",
}
_DB_ICONS = {
    "customers": "👥", "payments": "💸", "subscriptions": "🔄", "referrals": "🤝",
    "commissions": "💰", "flags": "🚩", "overview": "📈", "audit": "📜",
}

# Two-way control: the actions the owner can trigger from a Customer's Action field.
_ACTION_OPTIONS = ["grant_trial", "grant_monthly", "grant_yearly", "revoke",
                   "mark_blogger", "unmark_blogger"]
_ACTIONS: dict[str, tuple[str, object]] = {
    "grant_trial": ("grant", "trial"),
    "grant_monthly": ("grant", "monthly"),
    "grant_yearly": ("grant", "yearly"),
    "revoke": ("revoke", None),
    "mark_blogger": ("blogger", True),
    "unmark_blogger": ("blogger", False),
}
# Properties added after schema v1 — PATCHed onto already-existing databases.
def _extra_props(key: str) -> dict | None:
    if key == "customers":
        return {"Action": n.s_select_options(_ACTION_OPTIONS), "Last Action": n.s_text()}
    return None


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
            # Two-way control: owner sets this to trigger a server-side action.
            "Action": n.s_select_options(_ACTION_OPTIONS), "Last Action": n.s_text(),
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
    if key == "overview":
        return {
            "Date": n.s_title(), "Customers": n.s_number(), "Active": n.s_number(),
            "Paid": n.s_number(), "Trial": n.s_number(), "New (24h)": n.s_number(),
            "Revenue": n.s_number("dollar"), "Payments": n.s_number(),
            "Pending invoices": n.s_number(), "Commissions": n.s_number("dollar"),
            "Flagged keys": n.s_number(), "Abuse events": n.s_number(),
        }
    if key == "audit":
        return {
            "Event": n.s_title(), "Actor": n.s_text(), "Action": n.s_select(),
            "Target": n.s_text(), "When": n.s_date(),
        }
    raise KeyError(key)


def _customer_icon(status: str, plan: str) -> str:
    if status != "active":
        return "⚪"
    return "🧪" if plan == "trial" else "💎"


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


def overview_props(date_str: str, *, customers, active, paid, trial, new24h, revenue,
                   payments, pending, commissions, flagged, abuse) -> dict:
    return {
        "Date": n.title(date_str),
        "Customers": n.number(customers), "Active": n.number(active),
        "Paid": n.number(paid), "Trial": n.number(trial), "New (24h)": n.number(new24h),
        "Revenue": n.number(revenue), "Payments": n.number(payments),
        "Pending invoices": n.number(pending), "Commissions": n.number(commissions),
        "Flagged keys": n.number(flagged), "Abuse events": n.number(abuse),
    }


def audit_props(a) -> dict:
    return {
        "Event": n.title(f"{a.action} #{a.id}"),
        "Actor": n.text(a.actor),
        "Action": n.select(a.action),
        "Target": n.text(a.target),
        "When": n.date(a.created_at),
    }


def content_hash(props: dict) -> str:
    return hashlib.sha256(json.dumps(props, sort_keys=True, default=str).encode()).hexdigest()


# ─── Upsert + reconcile ──────────────────────────────────────────────────────
class _Budget:
    def __init__(self, limit: int) -> None:
        self.left = limit


async def _upsert(db, mappings, budget, *, kind, ref, db_id, props, icon=None) -> str | None:
    """Create/update one Notion page idempotently; return its page id (or None)."""
    h = content_hash({"props": props, "icon": icon})
    row = mappings.get((kind, ref))
    if row is None:
        if budget.left <= 0:
            return None  # defer creation to a later pass
        try:
            page_id = await n.create_page(db_id, props, icon=icon)
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
            await n.update_page(row.notion_id, properties=props, icon=icon)
        except Exception as exc:  # noqa: BLE001
            log.warning("notion update %s/%s failed: %s", kind, ref, exc)
            return row.notion_id
        row.content_hash = h
        budget.left -= 1
    return row.notion_id


async def _ensure_databases(db, mappings) -> dict[str, str] | None:
    """Create any missing databases (with icons) and evolve existing ones.

    The db mapping's content_hash stores the schema version; when it lags
    _SCHEMA_VERSION we PATCH the database to add new properties / set its icon,
    so schema changes reach workspaces created by an older build.
    """
    ids: dict[str, str] = {}
    created = False
    for key in _DB_ORDER:
        icon = n.emoji_icon(_DB_ICONS.get(key))
        row = mappings.get(("database", key))
        if row is not None:
            ids[key] = row.notion_id
            if row.content_hash != _SCHEMA_VERSION:
                try:
                    await n.update_database(row.notion_id, properties=_extra_props(key), icon=icon)
                    row.content_hash = _SCHEMA_VERSION
                    await db.commit()
                except Exception as exc:  # noqa: BLE001 - evolution is best-effort
                    log.warning("notion evolve database %s failed: %s", key, exc)
            continue
        try:
            db_id = await n.create_database(
                settings.notion_parent_page_id, _DB_TITLES[key], db_schema(key, ids), icon=icon
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("notion create database %s failed: %s", key, exc)
            return None
        row = NotionSync(kind="database", ref=key, notion_id=db_id, content_hash=_SCHEMA_VERSION)
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
            status = "active" if plan_name else "inactive"
            props = customer_props(
                u, plan=plan_name or "none", status=status,
                expires_at=expires_at, key_prefix=prefixes.get(u.id),
                devices=dev_counts.get(u.id, 0), referrals=ref_counts.get(u.id, 0),
                earnings=earn.get(u.id, 0),
            )
            pid = await _upsert(db, mappings, budget, kind="customer", ref=str(u.id),
                                db_id=ids["customers"], props=props,
                                icon=n.emoji_icon(_customer_icon(status, plan_name or "none")))
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

        # 7) Audit-log events.
        auds = list(await db.scalars(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(_SCAN_LIMIT)))
        for a in auds:
            await _upsert(db, mappings, budget, kind="audit", ref=str(a.id),
                          db_id=ids["audit"], props=audit_props(a))
        await db.commit()

        # 8) Overview — a daily KPI snapshot (one row per day, updated through it).
        await _sync_overview(db, ids, mappings, budget, now)
        await db.commit()

        return _MAX_WRITES_PER_RUN - budget.left
    finally:
        await redis_client.delete(redis_keys.sync_lock("notion"))


async def _sync_overview(db, ids, mappings, budget, now: datetime) -> None:
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    active = await db.scalar(
        select(func.count(func.distinct(Subscription.user_id))).where(
            Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at > now)
    ) or 0
    trial = await db.scalar(
        select(func.count(func.distinct(Subscription.user_id)))
        .select_from(Subscription).join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.status == SubscriptionStatus.ACTIVE,
               Subscription.expires_at > now, Plan.is_trial.is_(True))
    ) or 0
    revenue = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == PaymentStatus.PAID)
    ) or 0
    paid_count = await db.scalar(
        select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.PAID)) or 0
    pending = await db.scalar(
        select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.PENDING)) or 0
    commissions = await db.scalar(select(func.coalesce(func.sum(Commission.amount), 0))) or 0
    flagged = await db.scalar(
        select(func.count()).select_from(ApiKey).where(ApiKey.flagged.is_(True))) or 0
    abuse = await db.scalar(select(func.count()).select_from(AbuseEvent)) or 0
    new24h = await db.scalar(
        select(func.count()).select_from(User).where(User.created_at > now - timedelta(days=1))) or 0

    date_str = now.strftime("%Y-%m-%d")
    props = overview_props(
        date_str, customers=total, active=active, paid=active - trial, trial=trial,
        new24h=new24h, revenue=revenue, payments=paid_count, pending=pending,
        commissions=commissions, flagged=flagged, abuse=abuse,
    )
    await _upsert(db, mappings, budget, kind="overview", ref=date_str,
                  db_id=ids["overview"], props=props, icon=n.emoji_icon("📈"))


# ─── Instant push (best-effort, on a single user — e.g. right after payment) ──
async def _one_customer(db, user, now: datetime):
    """Compute one user's customer props + (status, plan) for an immediate push."""
    row = (await db.execute(
        select(Plan.name, Subscription.expires_at)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(Subscription.user_id == user.id,
               Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at > now)
        .order_by(Subscription.expires_at.desc()).limit(1)
    )).first()
    plan_name, expires_at = (row[0], row[1]) if row else (None, None)
    prefix = await db.scalar(
        select(ApiKey.prefix).where(ApiKey.user_id == user.id, ApiKey.status == ApiKeyStatus.ACTIVE)
        .order_by(ApiKey.created_at.desc()).limit(1))
    devices = await db.scalar(
        select(func.count(Device.id)).join(ApiKey, ApiKey.id == Device.key_id)
        .where(ApiKey.user_id == user.id, Device.status != DeviceStatus.REMOVED)) or 0
    referrals = await db.scalar(
        select(func.count()).select_from(Referral).where(Referral.referrer_user_id == user.id)) or 0
    earnings = await db.scalar(
        select(func.coalesce(func.sum(Commission.amount), 0))
        .where(Commission.referrer_user_id == user.id)) or 0
    status_label = "active" if plan_name else "inactive"
    props = customer_props(user, plan=plan_name or "none", status=status_label,
                           expires_at=expires_at, key_prefix=prefix, devices=devices,
                           referrals=referrals, earnings=earnings)
    return props, status_label, (plan_name or "none")


async def push_user(db: AsyncSession, user_id: int) -> None:
    """Immediately mirror one customer (+ their latest payment) to Notion.

    Best-effort and self-guarded. Skips if a full reconcile holds the lock (the
    periodic pass will cover it) or if the databases aren't provisioned yet.
    """
    if not is_enabled():
        return
    try:
        got = await redis_client.set(redis_keys.sync_lock("notion"), "1", nx=True, ex=60)
        if not got:
            return
        try:
            mappings = await _load_mappings(db)
            ids = {k: r.notion_id for (kind, k), r in mappings.items() if kind == "database"}
            if "customers" not in ids:
                return
            budget = _Budget(10)
            now = datetime.now(UTC)
            user = await db.get(User, user_id)
            if user is None:
                return
            props, status_label, plan_name = await _one_customer(db, user, now)
            cp = await _upsert(db, mappings, budget, kind="customer", ref=str(user.id),
                               db_id=ids["customers"], props=props,
                               icon=n.emoji_icon(_customer_icon(status_label, plan_name)))
            if cp and "payments" in ids:
                p = await db.scalar(
                    select(Payment).where(Payment.user_id == user.id)
                    .order_by(Payment.id.desc()).limit(1))
                if p:
                    await _upsert(db, mappings, budget, kind="payment", ref=str(p.id),
                                  db_id=ids["payments"], props=payment_props(p, customer_page=cp))
        finally:
            await redis_client.delete(redis_keys.sync_lock("notion"))
    except Exception as exc:  # noqa: BLE001 - never affect the caller (webhook/admin)
        log.warning("notion push_user failed: %s", exc)


# ─── Two-way control: apply actions set from a Notion Customer row ───────────
async def _notify_safe(telegram_id: int, text: str) -> None:
    """DM the user without ever letting a notify/format issue mark an action failed."""
    try:
        await notify.send_message(telegram_id, text)
    except Exception as exc:  # noqa: BLE001 - the action already committed; DM is extra
        log.warning("notion action notify failed for %s: %s", telegram_id, exc)


async def _apply_one(db, user_id: int, spec: tuple[str, object], actor: str) -> None:
    """Apply one action via the server-side path. The DB commit is the success
    point; DMs run only after and can never turn a committed action into a failure."""
    kind, arg = spec
    user = await db.get(User, user_id)
    if user is None:
        return
    if kind == "grant":
        plan = await db.scalar(select(Plan).where(Plan.name == arg))
        if plan is None:
            return
        result = await activation.grant(db, user=user, plan=plan, payment=None, actor=actor)
        await db.commit()
        msg = (f"🎁 You've been granted <b>{result.plan_name}</b> until "
               f"{result.expires_at:%Y-%m-%d}.")
        if result.new_key_raw:
            msg += f"\n\n🔑 <b>Your API key (shown once):</b>\n<code>{result.new_key_raw}</code>"
        await _notify_safe(user.telegram_id, msg)
    elif kind == "revoke":
        await revocation.revoke_user(db, user_id=user.id, actor=actor)
        await db.commit()
        await _notify_safe(
            user.telegram_id, "⚠️ Your access has been revoked. Contact support if unexpected.")
    elif kind == "blogger":
        user.is_blogger = bool(arg)
        await record_audit(db, actor=actor, action="set_blogger",
                           target=str(user.id), meta={"value": bool(arg)})
        await db.commit()


async def apply_actions(db: AsyncSession) -> int:
    """Apply any actions the owner set on Customer rows in Notion (then clear them).

    Reset-first: the Notion field is cleared BEFORE the action runs, so a crash
    can never double-apply (a grant adding duration twice). Routed through the
    same server-side services as admin commands — never bypasses entitlement.
    """
    if not (is_enabled() and settings.notion_allow_actions):
        return 0
    mappings = await _load_mappings(db)
    cust_db = mappings.get(("database", "customers"))
    if cust_db is None:
        return 0
    # Reverse map page -> user. notion_id is unique by construction; if a
    # duplicate ever appears (data corruption / restored row) mark it ambiguous
    # so we never apply an action to the wrong user.
    page_to_user: dict[str, int | None] = {}
    for (kind, ref), r in mappings.items():
        if kind != "customer":
            continue
        if r.notion_id in page_to_user:
            log.warning("notion: duplicate page id %s across customer rows — skipping", r.notion_id)
            page_to_user[r.notion_id] = None
            continue
        page_to_user[r.notion_id] = int(ref)
    try:
        pages = await n.query_database(
            cust_db.notion_id,
            filter={"property": "Action", "select": {"is_not_empty": True}})
    except Exception as exc:  # noqa: BLE001
        log.warning("notion query actions failed: %s", exc)
        return 0

    applied = 0
    for page in pages:
        pid = page.get("id")
        action = n.read_select(page.get("properties", {}).get("Action"))
        if not action or action not in _ACTIONS:
            continue
        user_id = page_to_user.get(pid)
        if user_id is None:
            continue
        # Attribute to the Notion user who set the field, when available.
        editor = (page.get("last_edited_by") or {}).get("id")
        actor = f"notion:{editor}" if editor else "notion"
        # Reset-first (fail-safe: never double-apply on a later poll).
        try:
            await n.update_page(pid, properties={
                "Action": n.select(None),
                "Last Action": n.text(f"{action} @ {now_str()}"),
            })
        except Exception as exc:  # noqa: BLE001
            log.warning("notion reset action failed for %s: %s", pid, exc)
            continue
        try:
            await _apply_one(db, user_id, _ACTIONS[action], actor)
            applied += 1
            log.info("notion action %s applied to user %s", action, user_id)
        except Exception as exc:  # noqa: BLE001
            # Reset already cleared the field, so this won't double-apply; surface
            # the failure to the owner instead of silently dropping it.
            log.error("notion action %s for user %s failed: %s", action, user_id, exc)
            try:
                await n.update_page(pid, properties={
                    "Last Action": n.text(f"{action} FAILED @ {now_str()}")})
            except Exception:  # noqa: BLE001
                pass
    return applied


def now_str() -> str:
    return f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC"


async def status(db: AsyncSession) -> dict:
    """Lightweight status for the /notion admin command (no Notion API calls)."""
    mappings = await _load_mappings(db)
    dbs = {k: r.notion_id for (kind, k), r in mappings.items() if kind == "database"}
    synced = sum(1 for (kind, _) in mappings if kind != "database")
    return {
        "enabled": is_enabled(),
        "configured": bool(settings.notion_api_key != "CHANGE_ME" and settings.notion_parent_page_id),
        "actions": bool(settings.notion_allow_actions),
        "databases": dbs,
        "synced_pages": synced,
    }
