"""Admin commands, gated by ADMIN_IDS.

/stats, /grant <telegram_id> <plan>, /revoke <telegram_id>, /flags,
/unflag <key_prefix|key_id>. Grants/revocations reuse the same server-side
activation/revocation services as the payment webhook.
"""

from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import BufferedInputFile, LinkPreviewOptions, Message
from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import SessionFactory
from app.core.logging import get_logger
from app.models.abuse_event import AbuseEvent
from app.models.api_key import ApiKey
from app.models.enums import PaymentStatus, SubscriptionStatus
from app.models.feedback import Feedback
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.promo_code import DISCOUNT_PERCENT
from app.models.referral import Commission, Referral
from app.models.session import Session
from app.models.subscription import Subscription
from app.models.user import User
from app.services import activation, devices as devices_svc
from app.services import (
    bot_content,
    club,
    handoff,
    keys,
    notifications,
    notion_sync,
    promos,
    revocation,
    subscriptions,
    users,
)
from app.services.audit import record_audit
from app.bot import notify

router = Router(name="admin")
log = get_logger("admin")


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in settings.admin_ids)


# Gate every handler in this router behind the admin check.
router.message.filter(IsAdmin())


@router.message(Command("clubstatus"))
async def clubstatus_cmd(message: Message) -> None:
    """Operator one-glance check: is the subscriber group wired up correctly?"""
    if not club.is_enabled():
        await message.answer(
            "👥 Subscriber group: <b>disabled</b> (set CLIENT_GROUP_ID + a real BOT_TOKEN).")
        return
    verdict = await club.preflight()
    async with SessionFactory() as db:
        try:
            n = await db.scalar(
                select(func.count()).select_from(User).where(User.club_member.is_(True)))
            db_line = f"In group (club_member=true): <b>{n}</b>"
        except Exception as exc:  # noqa: BLE001 - surface a schema-behind hint instead of crashing
            db_line = f"DB check failed (schema behind? run migrations): {exc}"
    await message.answer(f"👥 <b>Subscriber group</b>\nConfig: {verdict}\n{db_line}")


@router.message(Command("stats"))
async def stats_cmd(message: Message) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db:
        total_users = await db.scalar(select(func.count()).select_from(User))
        active_users = await db.scalar(
            select(func.count(func.distinct(Subscription.user_id))).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at > now,
            )
        )
        # Split active subscriptions into trial vs paid via the plan flag.
        trials_active = await db.scalar(
            select(func.count(func.distinct(Subscription.user_id)))
            .select_from(Subscription).join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.status == SubscriptionStatus.ACTIVE,
                   Subscription.expires_at > now, Plan.is_trial.is_(True))
        )
        paid_active = (active_users or 0) - (trials_active or 0)
        active_sessions = await db.scalar(
            select(func.count()).select_from(Session).where(
                Session.revoked.is_(False), Session.expires_at > now
            )
        )
        revenue = await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.PAID
            )
        )
        paid_count = await db.scalar(
            select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.PAID)
        )
        pending_count = await db.scalar(
            select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.PENDING)
        )
        commissions_paid = await db.scalar(
            select(func.coalesce(func.sum(Commission.amount), 0))
        )
        flagged = await db.scalar(
            select(func.count()).select_from(ApiKey).where(ApiKey.flagged.is_(True))
        )
        abuse_total = await db.scalar(select(func.count()).select_from(AbuseEvent))
    await message.answer(
        "<b>📊 Stats</b>\n"
        f"👥 Users: {total_users or 0} total · {active_users or 0} active\n"
        f"   ├ paid: {paid_active}\n"
        f"   └ trial: {trials_active or 0}\n"
        f"🔌 Live sessions: {active_sessions or 0}\n"
        f"💰 Revenue (paid): {revenue or 0}  ({paid_count or 0} payments)\n"
        f"🧾 Pending invoices: {pending_count or 0}\n"
        f"🤝 Referral commissions: {commissions_paid or 0}\n"
        f"🚩 Flagged keys: {flagged or 0}\n"
        f"⚠️ Abuse events (total): {abuse_total or 0}",
        parse_mode="HTML",
    )


@router.message(Command("user"))
async def user_cmd(message: Message, command: CommandObject) -> None:
    """/user <telegram_id> — full profile: plan, key, devices, risk, referrals."""
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Usage: /user &lt;telegram_id&gt;", parse_mode="HTML")
        return
    telegram_id = int(arg)
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, telegram_id)
        if user is None:
            await message.answer("No such user.")
            return
        active = await subscriptions.get_active_with_plan(db, user.id)
        key = await keys.get_active_key(db, user.id)
        device_count = (
            len(await devices_svc.list_for_key(db, key.id)) if key else 0
        )
        referrals_made = await db.scalar(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_user_id == user.id
            )
        )
        earned = await db.scalar(
            select(func.coalesce(func.sum(Commission.amount), 0)).where(
                Commission.referrer_user_id == user.id
            )
        )
    uname = f"@{user.username}" if user.username else "(no username)"
    if active is None:
        sub_line = "none"
    else:
        sub, plan = active
        sub_line = f"{plan.name} ({sub.status}), expires {sub.expires_at:%Y-%m-%d}"
    key_line = f"<code>{key.prefix}…</code>" if key else "none"
    flag = " 🚩" if (key and key.flagged) else ""
    badge = " ⭐blogger" if user.is_blogger else ""
    await message.answer(
        f"<b>👤 User {telegram_id}</b>{badge}\n"
        f"Handle: {uname}\n"
        f"Language: {user.language}\n"
        f"Risk score: {user.risk_score}\n"
        f"Subscription: {sub_line}\n"
        f"API key: {key_line}{flag}\n"
        f"Devices: {device_count}\n"
        f"Referred by: {user.referred_by or '—'}\n"
        f"Referrals made: {referrals_made or 0} · earned: {earned or 0}\n\n"
        f"Actions: /grant {telegram_id} &lt;plan&gt; · /revoke {telegram_id} · "
        f"/reply {telegram_id} &lt;msg&gt;",
        parse_mode="HTML",
    )


@router.message(Command("notion"))
async def notion_cmd(message: Message, command: CommandObject) -> None:
    """/notion — sync status; /notion sync — reconcile to Notion now."""
    arg = (command.args or "").strip().lower()
    if not notion_sync.is_enabled():
        await message.answer(
            "🔌 <b>Notion sync is off.</b>\n"
            "Set NOTION_SYNC_ENABLED=true, NOTION_API_KEY and NOTION_PARENT_PAGE_ID "
            "in .env (see deploy/notion.md), then restart.",
            parse_mode="HTML",
        )
        return
    if arg == "sync":
        await message.answer("⏳ Syncing to Notion…")
        try:
            async with SessionFactory() as db:
                written = await notion_sync.reconcile(db)
        except Exception as exc:  # noqa: BLE001 - report, never crash the command
            log.warning("/notion sync failed: %s", exc)
            await message.answer("⚠️ Notion sync failed — see logs.")
            return
        if written is None:
            await message.answer("⏳ A Notion sync is already running — try again shortly.")
        else:
            await message.answer(f"✅ Notion sync done — {written} page(s) created/updated.")
        return
    try:
        async with SessionFactory() as db:
            st = await notion_sync.status(db)
    except Exception as exc:  # noqa: BLE001
        log.warning("/notion status failed: %s", exc)
        await message.answer("⚠️ Could not read Notion status — see logs.")
        return
    lines = ["<b>🗂 Notion sync</b>", f"Synced pages: {st['synced_pages']}"]
    if st["databases"]:
        lines.append("\n<b>Databases</b>")
        for key, nid in st["databases"].items():
            lines.append(f"• <a href=\"{notion_sync.page_url(nid)}\">{key}</a>")
    else:
        lines.append("No databases yet — run <code>/notion sync</code> to create them.")
    if st.get("actions"):
        lines.append("\n🔁 Two-way actions <b>on</b> — set a Customer's <i>Action</i> "
                     "field (grant/revoke/blogger) and the bot applies it.")
    lines.append("\nRun <code>/notion sync</code> to push the latest data now.")
    await message.answer("\n".join(lines), parse_mode="HTML",
                         link_preview_options=LinkPreviewOptions(is_disabled=True))


@router.message(Command("admin"))
async def admin_help_cmd(message: Message) -> None:
    await message.answer(
        "<b>🛠 Admin commands</b>\n"
        "/stats — overview (users, revenue, flags)\n"
        "/user &lt;id&gt; — full profile of one user\n"
        "/grant &lt;id&gt; &lt;plan&gt; — grant/extend access\n"
        "/revoke &lt;id&gt; — kill keys & sessions\n"
        "/flags — flagged keys & recent abuse\n"
        "/unflag &lt;prefix|id&gt; — clear a flag\n"
        "/notion [sync] — Notion CRM status / sync now\n"
        "/broadcast &lt;msg&gt; — message every user\n"
        "/push &lt;segment&gt; &lt;msg&gt; — message a segment (opted-in)\n"
        "/announce [topic= ] [pin] &lt;msg&gt; — post in the subscriber group\n"
        "/promonew &lt;code&gt; &lt;20%|$10&gt; [plan=] [max=] [days=] — new code\n"
        "/promoedit &lt;code&gt; … — change a code (amount/plan/max/days/on|off)\n"
        "/promos — list discount codes\n"
        "/promooff &lt;code&gt; — deactivate a code\n"
        "/content — edit bot copy (welcome, banner, description, about)\n"
        "/feedback — view recent client feedback\n"
        "/export — download customers CSV\n"
        "/reply &lt;id&gt; &lt;msg&gt; — answer a support handoff\n"
        "/close &lt;id&gt; — end a support handoff",
        parse_mode="HTML",
    )


@router.message(Command("broadcast"))
async def broadcast_cmd(message: Message, command: CommandObject) -> None:
    """/broadcast <message> — DM the message (HTML) to every user."""
    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage: /broadcast &lt;message&gt;", parse_mode="HTML")
        return
    async with SessionFactory() as db:
        ids = list(await db.scalars(select(User.telegram_id)))
    await message.answer(f"📣 Sending to {len(ids)} user(s)…")
    sent = failed = 0
    for tid in ids:
        try:
            await message.bot.send_message(tid, text)
            sent += 1
        except Exception:  # noqa: BLE001 - a blocked/invalid chat must not stop the rest
            failed += 1
        await asyncio.sleep(0.05)  # stay well under Telegram's ~30 msg/s limit
    await message.answer(f"📣 Broadcast done — {sent} sent, {failed} failed.")


def _parse_announce(arg: str) -> tuple[int | None, bool, str]:
    """Pull optional leading `topic=<id>` / `pin` flags off an /announce arg.

    Flags are only recognised at the very front; the first non-flag token starts
    the message body, whose internal spacing and newlines are preserved verbatim
    (so multi-line HTML announcements survive intact)."""
    topic_id: int | None = None
    pin = False
    rest = arg
    while True:
        parts = rest.split(None, 1)  # first token + untouched remainder
        if not parts:
            break
        head = parts[0]
        low = head.lower()
        if low == "pin":
            pin = True
        elif low.startswith("topic=") and head.split("=", 1)[1].lstrip("-").isdigit():
            topic_id = int(head.split("=", 1)[1])
        else:
            break
        rest = parts[1] if len(parts) > 1 else ""
    return topic_id, pin, rest.strip()


@router.message(Command("announce"))
async def announce_cmd(message: Message, command: CommandObject) -> None:
    """/announce [topic=<id>] [pin] <message> — post into the subscriber group.

    HTML allowed. `pin` pins the post; `topic=<thread_id>` targets a forum topic."""
    if not club.is_enabled():
        await message.answer(
            "👥 Subscriber group isn't configured "
            "(set CLIENT_GROUP_ID + a real BOT_TOKEN). See /clubstatus.")
        return
    topic_id, pin, text = _parse_announce(command.args or "")
    if not text:
        await message.answer(
            "📣 <b>Post to the subscriber group</b>\n"
            "<code>/announce [topic=&lt;id&gt;] [pin] &lt;message&gt;</code>\n\n"
            "HTML allowed. <code>pin</code> pins it; <code>topic=123</code> posts into a "
            "forum topic thread (the number after the last <code>/</code> in a topic's link).",
            parse_mode="HTML")
        return
    try:
        mid = await club.announce(text, topic_id=topic_id, pin=pin)
    except Exception as exc:  # noqa: BLE001 - report Telegram/config errors to the admin
        log.warning("/announce failed: %s", exc)
        await message.answer(f"⚠️ Couldn't post to the group: {exc}")
        return
    extras = []
    if topic_id is not None:
        extras.append(f"topic {topic_id}")
    if pin:
        extras.append("pinned")
    tail = f" ({', '.join(extras)})" if extras else ""
    await message.answer(f"✅ Posted to the subscriber group{tail} — message id {mid}.")


@router.message(Command("feedback"))
async def feedback_view_cmd(message: Message) -> None:
    """/feedback — show the latest client suggestions submitted via 💬 Feedback."""
    async with SessionFactory() as db:
        rows = list(await db.execute(
            select(Feedback, User.username, User.telegram_id)
            .join(User, User.id == Feedback.user_id)
            .order_by(Feedback.id.desc()).limit(15)))
    if not rows:
        await message.answer("No feedback yet. 💬")
        return
    lines = ["<b>💡 Recent feedback</b>"]
    for fb, uname, tid in rows:
        who = f"@{uname}" if uname else f"id {tid}"
        lines.append(f"\n• {who} ({fb.created_at:%Y-%m-%d}):\n{fb.text}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("push"))
async def push_cmd(message: Message, command: CommandObject) -> None:
    """/push <all|active|trial|inactive> <message> — DM a segment (opted-in only)."""
    parts = (command.args or "").split(maxsplit=1)
    if len(parts) < 2 or parts[0].lower() not in notifications.SEGMENTS:
        await message.answer(
            "Usage: /push &lt;all|active|trial|inactive&gt; &lt;message&gt;\n"
            "(only reaches users who haven't opted out — use /broadcast for everyone)",
            parse_mode="HTML")
        return
    segment, text = parts[0].lower(), parts[1]
    async with SessionFactory() as db:
        ids = await notifications.segment_telegram_ids(db, segment)
    await message.answer(f"🔔 Pushing to {len(ids)} '{segment}' user(s)…")
    sent = failed = 0
    for tid in ids:
        try:
            await message.bot.send_message(tid, text)
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(f"🔔 Push done — {sent} sent, {failed} failed.")


@router.message(Command("export"))
async def export_cmd(message: Message) -> None:
    """/export — send a CSV of all customers (plan, expiry, referrals, earnings)."""
    now = datetime.now(UTC)
    async with SessionFactory() as db:
        users = list(await db.scalars(select(User).order_by(User.id)))
        active = {
            uid: (plan, exp) for uid, plan, exp in (await db.execute(
                select(Subscription.user_id, Plan.name, Subscription.expires_at)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.status == SubscriptionStatus.ACTIVE,
                       Subscription.expires_at > now)
                .order_by(Subscription.expires_at.desc()))).all()
        }
        earnings = dict((await db.execute(
            select(Commission.referrer_user_id, func.coalesce(func.sum(Commission.amount), 0))
            .group_by(Commission.referrer_user_id))).all())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["telegram_id", "username", "language", "plan", "expires",
                "risk", "blogger", "referred_by", "earned"])
    for u in users:
        plan, exp = active.get(u.id, ("", ""))
        w.writerow([u.telegram_id, u.username or "", u.language, plan,
                    f"{exp:%Y-%m-%d}" if exp else "", u.risk_score,
                    "yes" if u.is_blogger else "no", u.referred_by or "",
                    earnings.get(u.id, 0)])
    doc = BufferedInputFile(buf.getvalue().encode(), filename=f"customers-{now:%Y%m%d}.csv")
    await message.answer_document(doc, caption=f"📑 {len(users)} customer(s) exported.")


# Words that mean "no restriction" for plan / cap / expiry (friendly clearing).
_CLEAR_WORDS = {"*", "any", "none", "off", "unlimited", "never", "0"}


@dataclass
class _PromoArgs:
    code: str | None = None
    discount_type: str | None = None
    value: Decimal | None = None
    plan: str | None = None
    cap: str | None = None      # raw; validated by _limit_arg
    days: str | None = None     # raw; validated by _limit_arg
    active: bool | None = None  # set by a standalone on/off token


def _parse_promo_args(arg_str: str) -> _PromoArgs:
    """Forgiving parse of the admin promo syntax. Accepts the amount as 20% / $10
    / 'pct 20' / 'fixed 10', named flags (plan=/max=/days=) in any order, a
    standalone on/off, and legacy positional [plan] [max] [days]."""
    flags: dict[str, str] = {}
    positional: list[str] = []
    active: bool | None = None
    for t in arg_str.split():
        low = t.lower()
        if low in ("on", "off") and "=" not in t:
            active = low == "on"
        elif "=" in t and not t.startswith("="):
            k, v = t.split("=", 1)
            flags[k.lower().strip()] = v.strip()
        else:
            positional.append(t)
    out = _PromoArgs(active=active)
    if not positional:
        out.plan, out.cap, out.days = flags.get("plan"), flags.get("max"), flags.get("days")
        return out
    out.code = positional[0]
    rest = positional[1:]
    parsed = promos.parse_discount(rest)
    leftover = rest
    if parsed is not None:
        out.discount_type, out.value, consumed = parsed
        leftover = rest[consumed:]
    out.plan = flags.get("plan") or (leftover[0] if len(leftover) >= 1 else None)
    out.cap = flags.get("max") or (leftover[1] if len(leftover) >= 2 else None)
    out.days = flags.get("days") or (leftover[2] if len(leftover) >= 3 else None)
    return out


def _limit_arg(raw: str | None) -> tuple[str, int | None]:
    """Interpret a max/days argument → ('keep'|'clear'|'set'|'bad', value)."""
    if raw is None:
        return ("keep", None)
    if raw.lower() in _CLEAR_WORDS:
        return ("clear", None)
    if raw.isdigit() and int(raw) > 0:
        return ("set", int(raw))
    return ("bad", None)


def _promo_summary(promo, plan_name: str | None) -> str:
    desc = promos.describe(promo)
    scope = plan_name or "any plan"
    cap = f"{promo.max_redemptions} uses" if promo.max_redemptions else "unlimited"
    exp = f"expires {promo.expires_at:%Y-%m-%d}" if promo.expires_at else "no expiry"
    status = "" if promo.is_active else " · OFF"
    return f"<b>{promo.code}</b> — {desc}, {scope}, {cap}, {exp}{status}"


_PROMO_NEW_USAGE = (
    "🏷 <b>Create a discount code</b>\n"
    "<code>/promonew CODE AMOUNT [plan=…] [max=…] [days=…]</code>\n\n"
    "<b>AMOUNT</b> — any of: <code>20%</code> · <code>$10</code> · "
    "<code>pct 20</code> · <code>fixed 10</code>\n"
    "<b>Optional</b> (any order, omit to skip): <code>plan=monthly</code> · "
    "<code>max=100</code> · <code>days=30</code>\n\n"
    "Examples:\n"
    "• <code>/promonew SAVE20 20%</code> — 20% off everything, no limit\n"
    "• <code>/promonew WELCOME10 $10 plan=monthly max=100 days=30</code>"
)


@router.message(Command("promonew"))
async def promonew_cmd(message: Message, command: CommandObject) -> None:
    """Create a discount code with a forgiving syntax (20% / $10 / pct 20)."""
    spec = _parse_promo_args(command.args or "")
    if not spec.code or spec.discount_type is None or spec.value is None:
        await message.answer(_PROMO_NEW_USAGE, parse_mode="HTML")
        return
    if spec.value <= 0 or (spec.discount_type == DISCOUNT_PERCENT and spec.value > 100):
        await message.answer("Percent must be 1–100; a fixed amount must be positive.")
        return
    cap_action, cap = _limit_arg(spec.cap)
    days_action, days = _limit_arg(spec.days)
    if cap_action == "bad":
        await message.answer("max must be a positive number (or omit it).")
        return
    if days_action == "bad":
        await message.answer("days must be a positive number (or omit it).")
        return
    max_redemptions = cap if cap_action == "set" else None
    expires_at = datetime.now(UTC) + timedelta(days=days) if days_action == "set" else None

    async with SessionFactory() as db:
        if await promos.get(db, spec.code) is not None:
            await message.answer(
                f"A code '{promos.normalize(spec.code)}' already exists — "
                f"use /promoedit to change it.")
            return
        plan_id, plan_name = None, None
        if spec.plan and spec.plan.lower() not in _CLEAR_WORDS:
            plan = await db.scalar(select(Plan).where(Plan.name == spec.plan.lower()))
            if plan is None:
                await message.answer(f"Unknown plan '{spec.plan}'.")
                return
            plan_id, plan_name = plan.id, plan.name
        promo = await promos.create(
            db, code=spec.code, discount_type=spec.discount_type, discount_value=spec.value,
            plan_id=plan_id, max_redemptions=max_redemptions, expires_at=expires_at,
            actor=f"admin:{message.from_user.id}",
        )
        await db.commit()
        summary = _promo_summary(promo, plan_name)
    await message.answer(f"✅ Created {summary}", parse_mode="HTML")


@router.message(Command("promos"))
async def promos_cmd(message: Message) -> None:
    """/promos — list discount codes with their redemption counts."""
    async with SessionFactory() as db:
        rows = await promos.list_all(db)
    if not rows:
        await message.answer("No promo codes yet. Create one with /promonew.")
        return
    lines = ["<b>🏷 Promo codes</b>"]
    for promo, plan_name in rows:
        desc = promos.describe(promo)
        used = f"{promo.times_redeemed}"
        if promo.max_redemptions is not None:
            used += f"/{promo.max_redemptions}"
        flags = []
        if not promo.is_active:
            flags.append("off")
        if promo.expires_at is not None:
            expired = promo.expires_at <= datetime.now(UTC)
            flags.append("expired" if expired else f"till {promo.expires_at:%Y-%m-%d}")
        scope = plan_name or "any"
        tail = f" [{', '.join(flags)}]" if flags else ""
        lines.append(
            f"• <code>{promo.code}</code> — {desc} · {scope} · used {used}{tail}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("promooff"))
async def promooff_cmd(message: Message, command: CommandObject) -> None:
    """/promooff <code> — deactivate a discount code."""
    code = (command.args or "").strip()
    if not code:
        await message.answer("Usage: /promooff &lt;code&gt;", parse_mode="HTML")
        return
    async with SessionFactory() as db:
        ok = await promos.deactivate(db, code=code, actor=f"admin:{message.from_user.id}")
        await db.commit()
    if ok:
        await message.answer(f"🚫 Deactivated <b>{promos.normalize(code)}</b>.", parse_mode="HTML")
    else:
        await message.answer(f"No code '{promos.normalize(code)}' found.")


_PROMO_EDIT_USAGE = (
    "✏️ <b>Edit a discount code</b>\n"
    "<code>/promoedit CODE [AMOUNT] [plan=…] [max=…] [days=…] [on|off]</code>\n\n"
    "Only the parts you include change. Use <code>any</code> / <code>never</code> "
    "to clear a plan / limit / expiry.\n\n"
    "Examples:\n"
    "• <code>/promoedit SAVE20 30%</code> — change it to 30% off\n"
    "• <code>/promoedit SAVE20 max=50 days=14</code> — cap 50 uses, expire in 14d\n"
    "• <code>/promoedit SAVE20 plan=any</code> — apply to all plans\n"
    "• <code>/promoedit SAVE20 off</code> — disable it"
)


@router.message(Command("promoedit"))
async def promoedit_cmd(message: Message, command: CommandObject) -> None:
    """Modify an existing code: only the fields you pass change."""
    spec = _parse_promo_args(command.args or "")
    if not spec.code:
        await message.answer(_PROMO_EDIT_USAGE, parse_mode="HTML")
        return
    kwargs: dict = {}
    if spec.discount_type is not None and spec.value is not None:
        if spec.value <= 0 or (spec.discount_type == DISCOUNT_PERCENT and spec.value > 100):
            await message.answer("Percent must be 1–100; a fixed amount must be positive.")
            return
        kwargs["discount_type"], kwargs["discount_value"] = spec.discount_type, spec.value
    if spec.active is not None:
        kwargs["is_active"] = spec.active

    cap_action, cap = _limit_arg(spec.cap)
    if cap_action == "bad":
        await message.answer("max must be a positive number, or 'any' to clear.")
        return
    if cap_action == "set":
        kwargs["max_redemptions"] = cap
    elif cap_action == "clear":
        kwargs["max_redemptions"] = None

    days_action, days = _limit_arg(spec.days)
    if days_action == "bad":
        await message.answer("days must be a positive number, or 'never' to clear.")
        return
    if days_action == "set":
        kwargs["expires_at"] = datetime.now(UTC) + timedelta(days=days)
    elif days_action == "clear":
        kwargs["expires_at"] = None

    async with SessionFactory() as db:
        if spec.plan is not None:
            if spec.plan.lower() in _CLEAR_WORDS:
                kwargs["plan_id"] = None
            else:
                plan = await db.scalar(select(Plan).where(Plan.name == spec.plan.lower()))
                if plan is None:
                    await message.answer(f"Unknown plan '{spec.plan}'.")
                    return
                kwargs["plan_id"] = plan.id
        if not kwargs:
            await message.answer(_PROMO_EDIT_USAGE, parse_mode="HTML")
            return
        promo = await promos.update(
            db, code=spec.code, actor=f"admin:{message.from_user.id}", **kwargs)
        if promo is None:
            await message.answer(
                f"No code '{promos.normalize(spec.code)}' found — create it with /promonew.")
            return
        plan_name = None
        if promo.plan_id is not None:
            plan_name = await db.scalar(select(Plan.name).where(Plan.id == promo.plan_id))
        await db.commit()
        summary = _promo_summary(promo, plan_name)
    await message.answer(f"✅ Updated {summary}", parse_mode="HTML")


# ─── Bot branding (admin-editable copy) ──────────────────────────────────────
async def _save_content(message: Message, key: str, value: str, apply_profile: bool) -> None:
    _, limit = bot_content.FIELDS[key]
    value = value.strip()
    if len(value) > limit:
        await message.answer(f"Too long — {key} is capped at {limit} characters.")
        return
    async with SessionFactory() as db:
        await bot_content.set_value(db, key, value, actor=f"admin:{message.from_user.id}")
        if apply_profile:
            await bot_content.apply_profile(message.bot, db)
        await db.commit()
    await message.answer(f"✅ Updated <b>{key}</b>.", parse_mode="HTML")


@router.message(Command("content"))
async def content_cmd(message: Message) -> None:
    """Show the editable bot copy + how to change each piece."""
    async with SessionFactory() as db:
        current = await bot_content.all_content(db)
    lines = ["<b>🎨 Bot content</b> (edit live, no redeploy)"]
    for key, (label, limit) in bot_content.FIELDS.items():
        val = current.get(key)
        if key == "banner":
            shown = "set ✅" if val else "—"
        else:
            shown = (val[:60] + "…") if val and len(val) > 60 else (val or "—")
        lines.append(f"\n• <b>{key}</b> — {label}\n  <i>{shown}</i>")
    lines.append(
        "\n\n<b>Commands</b>\n"
        "/setwelcome &lt;text&gt; — /start greeting\n"
        "/setbanner — reply to a photo (or send a photo captioned /setbanner)\n"
        "/setdescription &lt;text&gt; — the 'What can this bot do?' screen\n"
        "/setabout &lt;text&gt; — short profile bio\n"
        "/clearbanner — remove the /start banner")
    await message.answer("\n".join(lines), parse_mode="HTML",
                         link_preview_options=LinkPreviewOptions(is_disabled=True))


@router.message(Command("setwelcome"))
async def setwelcome_cmd(message: Message, command: CommandObject) -> None:
    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage: /setwelcome &lt;text&gt; (HTML allowed).", parse_mode="HTML")
        return
    await _save_content(message, "welcome", text, apply_profile=False)


@router.message(Command("setdescription"))
async def setdescription_cmd(message: Message, command: CommandObject) -> None:
    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage: /setdescription &lt;text&gt; (≤512 chars).", parse_mode="HTML")
        return
    await _save_content(message, "description", text, apply_profile=True)


@router.message(Command("setabout"))
async def setabout_cmd(message: Message, command: CommandObject) -> None:
    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage: /setabout &lt;text&gt; (≤120 chars).", parse_mode="HTML")
        return
    await _save_content(message, "about", text, apply_profile=True)


def _banner_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.reply_to_message and message.reply_to_message.photo:
        return message.reply_to_message.photo[-1].file_id
    return None


@router.message(Command("setbanner"))
async def setbanner_cmd(message: Message) -> None:
    fid = _banner_file_id(message)
    if not fid:
        await message.answer(
            "Send a photo, then <b>reply to it</b> with /setbanner — or send a photo "
            "with the caption <code>/setbanner</code>.", parse_mode="HTML")
        return
    await _save_content(message, "banner", fid, apply_profile=False)


@router.message(F.photo, F.caption.func(lambda c: bool(c) and c.strip().lower().startswith("/setbanner")))
async def setbanner_photo(message: Message) -> None:
    await _save_content(message, "banner", message.photo[-1].file_id, apply_profile=False)


@router.message(Command("clearbanner"))
async def clearbanner_cmd(message: Message) -> None:
    async with SessionFactory() as db:
        await bot_content.set_value(db, "banner", "", actor=f"admin:{message.from_user.id}")
        await db.commit()
    await message.answer("✅ Banner cleared — /start shows text only.")


@router.message(Command("grant"))
async def grant_cmd(message: Message, command: CommandObject) -> None:
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer("Usage: /grant &lt;telegram_id&gt; &lt;plan&gt;", parse_mode="HTML")
        return
    telegram_id, plan_name = int(parts[0]), parts[1].lower()
    async with SessionFactory() as db:
        plan = await db.scalar(select(Plan).where(Plan.name == plan_name))
        if plan is None:
            await message.answer(f"Unknown plan '{plan_name}'.")
            return
        user, _ = await users.get_or_create(db, telegram_id=telegram_id, username=None)
        result = await activation.grant(
            db, user=user, plan=plan, payment=None, actor=f"admin:{message.from_user.id}"
        )
        await db.commit()
        await notion_sync.push_user(db, user.id)  # mirror to Notion immediately

    if result.new_key_raw:
        await notify.send_message(
            telegram_id,
            f"🎁 You've been granted <b>{result.plan_name}</b> until "
            f"{result.expires_at:%Y-%m-%d}.\n\n"
            f"🔑 <b>Your API key (shown once):</b>\n<code>{result.new_key_raw}</code>",
        )
    else:
        await notify.send_message(
            telegram_id,
            f"🎁 Your access was granted/extended — <b>{result.plan_name}</b> until "
            f"{result.expires_at:%Y-%m-%d}.",
        )
    await message.answer(
        f"✅ Granted {result.plan_name} to {telegram_id} until {result.expires_at:%Y-%m-%d}."
    )


@router.message(Command("revoke"))
async def revoke_cmd(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Usage: /revoke &lt;telegram_id&gt;", parse_mode="HTML")
        return
    telegram_id = int(arg)
    async with SessionFactory() as db:
        user = await users.get_by_telegram_id(db, telegram_id)
        if user is None:
            await message.answer("No such user.")
            return
        await revocation.revoke_user(db, user_id=user.id, actor=f"admin:{message.from_user.id}")
        await db.commit()
    await message.answer(f"🚫 Revoked access for {telegram_id} (keys disabled, sessions killed).")
    await notify.send_message(telegram_id, "⚠️ Your access has been revoked. Contact support if unexpected.")


@router.message(Command("flags"))
async def flags_cmd(message: Message) -> None:
    async with SessionFactory() as db:
        flagged_keys = list(await db.scalars(
            select(ApiKey).where(ApiKey.flagged.is_(True)).order_by(ApiKey.id.desc()).limit(15)
        ))
        recent = list(await db.scalars(
            select(AbuseEvent).order_by(AbuseEvent.created_at.desc()).limit(10)
        ))
    if not flagged_keys and not recent:
        await message.answer("No flagged keys or abuse events. 🎉")
        return
    lines = ["<b>🚩 Flagged keys</b>"]
    for k in flagged_keys:
        lines.append(f"• id={k.id} prefix=<code>{k.prefix}</code> user={k.user_id}")
    lines.append("\n<b>Recent abuse events</b>")
    for e in recent:
        lines.append(f"• [{e.type}] key={e.key_id} — {e.detail or ''}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("unflag"))
async def unflag_cmd(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await message.answer("Usage: /unflag &lt;key_prefix|key_id&gt;", parse_mode="HTML")
        return
    async with SessionFactory() as db:
        if arg.isdigit():
            key = await db.scalar(select(ApiKey).where(ApiKey.id == int(arg)))
        else:
            key = await db.scalar(select(ApiKey).where(ApiKey.prefix == arg))
        if key is None:
            await message.answer("Key not found.")
            return
        key.flagged = False
        await record_audit(
            db, actor=f"admin:{message.from_user.id}", action="key_unflagged",
            target=str(key.id), meta={"prefix": key.prefix},
        )
        await db.commit()
    await message.answer(f"✅ Cleared flag on key id={key.id} (prefix {key.prefix}).")


@router.message(Command("reply"))
async def reply_cmd(message: Message, command: CommandObject) -> None:
    """/reply <telegram_id> <message> — answer a user in a human handoff."""
    parts = (command.args or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer("Usage: /reply &lt;telegram_id&gt; &lt;message&gt;", parse_mode="HTML")
        return
    target, text = int(parts[0]), parts[1]
    await handoff.enter(target)  # ensure the user stays in human mode
    await notify.send_message(target, f"🧑‍💼 <b>Support:</b> {text}")
    await message.answer(f"✅ Sent to {target}. (/close {target} to end the chat.)")


@router.message(Command("close"))
async def close_cmd(message: Message, command: CommandObject) -> None:
    """/close <telegram_id> — end a human handoff; user returns to the AI agent."""
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Usage: /close &lt;telegram_id&gt;", parse_mode="HTML")
        return
    target = int(arg)
    await handoff.exit(target)
    await notify.send_message(
        target, "✅ This support chat is closed. Ask me anything and the AI assistant will help again."
    )
    await message.answer(f"✅ Closed support chat with {target}.")
