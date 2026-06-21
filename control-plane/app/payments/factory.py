"""Select the active payment provider.

Crypto Pay is the default; falls back to the offline stub when no token is set
so local dev works without network or real credentials.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.payments.base import PaymentProvider
from app.payments.cryptopay import CryptoPayProvider
from app.payments.stub import StubProvider


@lru_cache
def get_provider() -> PaymentProvider:
    token = settings.cryptopay_api_token
    if token and token != "CHANGE_ME":
        return CryptoPayProvider()
    return StubProvider()


def get_cryptopay() -> CryptoPayProvider:
    """Webhook endpoint always validates against the Crypto Pay provider."""
    return CryptoPayProvider()
