"""Mini App API — the in-Telegram dashboard's backend.

Every request authenticates with the Telegram `initData` the Mini App sends in
`Authorization: tma <initData>` (verified HMAC + freshness). The endpoints mirror
the bot's read views (status / key / devices / referrals / plans) and let the
user start a purchase. All entitlement state stays server-side; the Mini App only
displays it and triggers the same server-side actions the bot does.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.gateway.deps import get_db
from app.models.enums import ReferralStatus
from app.models.plan import Plan
from app.models.referral import Commission, Referral
from app.models.user import User
from app.payments import telegram as tg
from app.services import (
    devices as devices_svc,
)
from app.services import (
    keys,
    payments,
    subscriptions,
    telegram_api,
    telegram_pay,
    users,
)
from app.webapp.auth import verify_init_data

router = APIRouter(prefix="/webapp/api", tags=["webapp"])


async def require_webapp_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("tma "):
        raise HTTPException(status_code=401, detail="missing init data")
    verified = verify_init_data(
        authorization[4:].strip(), settings.bot_token, max_age=settings.webapp_init_data_ttl)
    if verified is None:
        raise HTTPException(status_code=401, detail="invalid init data")
    user, _ = await users.get_or_create(
        db, telegram_id=verified.user_id, username=verified.username)
    await db.commit()
    return user


@router.get("/me")
async def me(user: User = Depends(require_webapp_user), db: AsyncSession = Depends(get_db)) -> dict:
    active = await subscriptions.get_active_with_plan(db, user.id)
    key = await keys.get_active_key(db, user.id)
    device_list = await devices_svc.list_for_key(db, key.id) if key else []

    sub_payload = None
    if active is not None:
        sub, plan = active
        sub_payload = {
            "plan": plan.name, "status": sub.status,
            "expires_at": sub.expires_at.isoformat(),
            "max_devices": plan.max_devices,
        }

    invited = await db.scalar(
        select(func.count()).select_from(Referral)
        .where(Referral.referrer_user_id == user.id)) or 0
    qualified = await db.scalar(
        select(func.count()).select_from(Referral)
        .where(Referral.referrer_user_id == user.id,
               Referral.status == ReferralStatus.QUALIFIED)) or 0
    earned = await db.scalar(
        select(func.coalesce(func.sum(Commission.amount), 0))
        .where(Commission.referrer_user_id == user.id)) or 0
    rate = settings.referral_rate_blogger if user.is_blogger else settings.referral_rate_standard
    bot_username = await telegram_api.get_bot_username()
    invite_link = (
        f"https://t.me/{bot_username}?start={user.telegram_id}" if bot_username else "")

    return {
        "telegram_id": user.telegram_id,
        "language": user.language,
        "subscription": sub_payload,
        "key_prefix": key.prefix if key else None,
        "key_flagged": bool(key.flagged) if key else False,
        "devices": [
            {"id": d.id, "fingerprint": d.fingerprint[:16], "status": d.status}
            for d in device_list
        ],
        "referrals": {
            "rate_pct": int(round(rate * 100)),
            "invited": invited, "qualified": qualified,
            "earned": f"{earned}", "invite_link": invite_link,
        },
    }


@router.get("/plans")
async def list_plans(_: User = Depends(require_webapp_user), db: AsyncSession = Depends(get_db)) -> dict:
    rows = await db.scalars(
        select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price))
    plans = [
        {
            "name": p.name, "price": f"{p.price}", "currency": p.currency,
            "duration_days": p.duration_days, "is_trial": p.is_trial,
            "max_devices": p.max_devices,
        }
        for p in rows
    ]
    methods = ["stars"] if settings.telegram_stars_enabled else []
    if settings.telegram_card_enabled and settings.telegram_provider_token not in ("", "CHANGE_ME"):
        methods.append("card")
    methods.append("crypto")
    return {"plans": plans, "methods": methods}


@router.post("/devices/{device_id}/remove")
async def remove_device(
    device_id: int, user: User = Depends(require_webapp_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    key = await keys.get_active_key(db, user.id)
    ok = await devices_svc.remove(db, key_id=key.id, device_id=device_id) if key else False
    await db.commit()
    return {"ok": ok}


@router.post("/buy")
async def buy(
    body: dict, user: User = Depends(require_webapp_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    plan_name = str(body.get("plan", "")).lower()
    method = str(body.get("method", "stars")).lower()
    code = body.get("code") or None

    resolved = await payments.resolve_checkout(db, user=user, plan_name=plan_name, armed_code=code)
    if resolved is None or resolved.plan.is_trial or resolved.plan.price <= 0:
        raise HTTPException(status_code=400, detail="unknown or non-purchasable plan")
    plan = resolved.plan
    promo_id = resolved.promo.id if resolved.promo else None
    title = f"{plan.name} subscription"
    desc = f"{plan.name} subscription — {plan.duration_days} days of full access."

    # 100%-off promo → grant immediately, no invoice.
    if resolved.final <= 0:
        result = await telegram_pay.grant_free(
            db, telegram_id=user.telegram_id, username=user.username,
            plan_id=plan.id, promo_code_id=promo_id)
        await db.commit()
        return {"status": "granted", "plan": plan.name,
                "expires_at": result.expires_at.isoformat() if result else None}

    if method == "crypto":
        _payment, pay_url = await payments.start_checkout(
            db, user=user, plan=plan, amount=resolved.final, promo=resolved.promo)
        await db.commit()
        return {"status": "link", "kind": "crypto", "url": pay_url}

    # Native Stars / card → an invoice link the Mini App opens with openInvoice.
    method_name = "telegram_stars" if method == "stars" else "telegram_card"
    payload = telegram_pay.build_payload(
        plan_id=plan.id, method=method_name, promo_code_id=promo_id)
    if method == "stars":
        ratio = (resolved.final / resolved.original) if resolved.original else Decimal(1)
        amount = tg.stars_amount(plan, usd_to_stars=settings.usd_to_stars, ratio=ratio)
        prices = [{"label": title[:32], "amount": amount}]
        currency, provider_token = tg.STARS_CURRENCY, ""
    else:  # card
        cents = int((resolved.final * 100).to_integral_value())
        prices = [{"label": title[:32], "amount": cents}]
        currency, provider_token = "USD", settings.telegram_provider_token
    await db.commit()

    link = await telegram_api.create_invoice_link(
        title=title, description=desc, payload=payload,
        currency=currency, prices=prices, provider_token=provider_token)
    return {"status": "link", "kind": "invoice", "url": link}
