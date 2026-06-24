"""Admin commands, gated by ADMIN_IDS.

/stats, /grant <telegram_id> <plan>, /revoke <telegram_id>, /flags,
/unflag <key_prefix|key_id>. Grants/revocations reuse the same server-side
activation/revocation services as the payment webhook.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionFactory
from app.models.abuse_event import AbuseEvent
from app.models.api_key import ApiKey
from app.models.enums import PaymentStatus, SubscriptionStatus
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.referral import Commission, Referral
from app.models.session import Session
from app.models.subscription import Subscription
from app.models.user import User
from app.services import activation, devices as devices_svc
from app.services import handoff, keys, revocation, subscriptions, users
from app.services.audit import record_audit
from app.bot import notify

router = Router(name="admin")


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in settings.admin_ids)


# Gate every handler in this router behind the admin check.
router.message.filter(IsAdmin())


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
        "/reply &lt;id&gt; &lt;msg&gt; — answer a support handoff\n"
        "/close &lt;id&gt; — end a support handoff",
        parse_mode="HTML",
    )


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
