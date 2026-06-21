"""Crypto Pay webhook signature verification + activation idempotency."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

from app.models.enums import PaymentStatus
from app.payments.cryptopay import CryptoPayProvider
from app.services import activation
from tests.factories import make_payment, make_plan, make_user

TOKEN = "test-token"


def _sign(body: bytes) -> str:
    secret = hashlib.sha256(TOKEN.encode()).digest()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_verify_webhook_accepts_valid_signature():
    provider = CryptoPayProvider(token=TOKEN)
    body = b'{"update_type":"invoice_paid","payload":{"invoice_id":1,"status":"paid"}}'
    assert provider.verify_webhook(body, _sign(body)) is True
    assert provider.verify_webhook(body, "deadbeef") is False
    assert provider.verify_webhook(body, None) is False


def test_parse_event_extracts_paid_invoice():
    provider = CryptoPayProvider(token=TOKEN)
    payload = {
        "update_type": "invoice_paid",
        "payload": {"invoice_id": 42, "status": "paid", "amount": "49", "fiat": "USD"},
    }
    event = provider.parse_event(payload)
    assert event is not None
    assert event.external_id == "42"
    assert event.status == "paid"
    assert event.amount == Decimal("49")
    assert event.currency == "USD"


def test_parse_event_ignores_non_paid_updates():
    provider = CryptoPayProvider(token=TOKEN)
    assert provider.parse_event({"update_type": "invoice_expired", "payload": {}}) is None


async def test_activation_is_idempotent(db):
    user = await make_user(db)
    plan = await make_plan(db, name="monthly", price="49.00", duration_days=30)
    await make_payment(db, user=user, plan=plan, external_id="inv-1")
    await db.commit()

    r1 = await activation.activate_paid_payment(
        db, external_id="inv-1", payer_fingerprint=None, amount=Decimal("49")
    )
    await db.commit()
    assert r1 is not None and r1.already_processed is False
    first_expiry = r1.expires_at

    # Replay the same paid webhook.
    r2 = await activation.activate_paid_payment(
        db, external_id="inv-1", payer_fingerprint=None, amount=Decimal("49")
    )
    await db.commit()
    assert r2 is not None and r2.already_processed is True
    # Subscription not double-extended.
    assert r2.expires_at == first_expiry


async def test_activation_marks_payment_paid_and_issues_key(db):
    user = await make_user(db)
    plan = await make_plan(db, name="monthly", price="49.00", duration_days=30)
    payment = await make_payment(db, user=user, plan=plan, external_id="inv-2")
    await db.commit()

    result = await activation.activate_paid_payment(
        db, external_id="inv-2", payer_fingerprint=None, amount=Decimal("49")
    )
    await db.commit()
    await db.refresh(payment)

    assert payment.status == PaymentStatus.PAID
    assert result.new_key_raw is not None  # first key issued, DM'd once
