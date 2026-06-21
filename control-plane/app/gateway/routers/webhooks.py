"""POST /webhooks/cryptopay — verify signature, then idempotently activate.

Hard rule: a forged or unsigned 'paid' call must grant nothing. The signature is
checked against the Crypto Pay provider before any DB state changes.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import notify
from app.core.logging import get_logger
from app.gateway.deps import DbDep
from app.payments.factory import get_cryptopay
from app.services import activation

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = get_logger("webhook")


@router.post("/cryptopay")
async def cryptopay_webhook(
    request: Request,
    crypto_pay_api_signature: str | None = Header(default=None),
    db: AsyncSession = DbDep,
) -> JSONResponse:
    body = await request.body()
    provider = get_cryptopay()

    # 1. Verify signature BEFORE doing anything.
    if not provider.verify_webhook(body, crypto_pay_api_signature):
        log.warning("rejected cryptopay webhook: bad signature")
        return JSONResponse(status_code=401, content={"error": "bad_signature"})

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "bad_json"})

    event = provider.parse_event(payload)
    if event is None or event.status != "paid":
        # Not an actionable paid event — ack so the provider stops retrying.
        return JSONResponse(content={"ok": True, "ignored": True})

    # 2. Idempotent activation (dedupe by external invoice id).
    result = await activation.activate_paid_payment(
        db,
        external_id=event.external_id,
        payer_fingerprint=event.payer_fingerprint,
        amount=event.amount,
    )
    await db.commit()

    if result is None:
        log.info("paid webhook for unknown invoice %s", event.external_id)
        return JSONResponse(content={"ok": True, "unknown_invoice": True})

    # 3. DM the user (new key shown once; otherwise a renewal note).
    if not result.already_processed:
        if result.new_key_raw:
            await notify.send_message(
                result.telegram_id,
                f"✅ Payment confirmed — <b>{result.plan_name}</b> active until "
                f"{result.expires_at:%Y-%m-%d}.\n\n"
                f"🔑 <b>Your API key (shown once):</b>\n<code>{result.new_key_raw}</code>\n\n"
                f"Store it securely — it will not be shown again.",
            )
        else:
            await notify.send_message(
                result.telegram_id,
                f"✅ Payment confirmed — <b>{result.plan_name}</b> extended until "
                f"{result.expires_at:%Y-%m-%d}. Your existing API key stays valid.",
            )

    return JSONResponse(content={"ok": True})
