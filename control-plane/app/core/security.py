"""Cryptographic primitives: API-key generation/hashing and short-lived JWTs.

- API keys are shown once; only sha256(key) + an 8-char prefix are persisted.
- Session tokens are server-signed JWTs, short-lived, and bound to a device
  fingerprint + session id so a leaked token cannot be reused on another device
  or after the session is revoked.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings

PREFIX_LEN = 8


@dataclass(frozen=True)
class GeneratedKey:
    raw: str        # shown to the user exactly once
    prefix: str     # stored for display/lookup hints
    key_hash: str   # sha256 hex — the only thing persisted for validation


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key() -> GeneratedKey:
    raw = secrets.token_urlsafe(32)
    return GeneratedKey(raw=raw, prefix=raw[:PREFIX_LEN], key_hash=hash_key(raw))


def fingerprint_digest(fingerprint: str) -> str:
    """Stable, non-reversible digest of a device fingerprint for token binding."""
    return hashlib.sha256(fingerprint.encode()).hexdigest()


def new_session_id() -> str:
    return uuid.uuid4().hex


def create_session_token(
    *,
    key_id: int,
    session_id: str,
    fingerprint: str,
    ttl_seconds: int | None = None,
) -> tuple[str, datetime]:
    """Sign a session JWT bound to the key, session id, and device fingerprint."""
    ttl = ttl_seconds or settings.jwt_ttl_seconds
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl)
    payload = {
        "sub": str(key_id),
        "sid": session_id,
        "dfp": fingerprint_digest(fingerprint),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_session_token(token: str) -> dict:
    """Verify signature + expiry and return claims. Raises jwt exceptions on failure."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# ─── Per-session request signing (anti-replay) ───────────────────────────────
# The signing secret is delivered ONCE at session creation and never re-sent.
# A passively sniffed protected request therefore can't be forged (no secret)
# and can't be replayed (nonce consumed + timestamp skew).

def new_signing_secret() -> str:
    return secrets.token_urlsafe(32)


def request_signature(
    *,
    secret: str,
    timestamp: str,
    nonce: str,
    method: str,
    path: str,
    body: bytes,
) -> str:
    body_digest = hashlib.sha256(body).hexdigest()
    msg = "\n".join([timestamp, nonce, method.upper(), path, body_digest])
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def verify_signature(expected: str, provided: str) -> bool:
    return hmac.compare_digest(expected, provided)
