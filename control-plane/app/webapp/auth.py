"""Telegram Mini App `initData` verification.

A Mini App hands the backend the signed `initData` query string. We verify it
per Telegram's spec before trusting any user identity:

  secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  check_hash = HMAC_SHA256(key=secret_key, msg=data_check_string)

where data_check_string is the `key=value` pairs (except `hash`) sorted by key
and joined with '\n'. A constant-time compare against the supplied `hash`, plus
an `auth_date` freshness check, gates every Mini App request. Never trust the
`user` field without this — it is attacker-controlled otherwise.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


@dataclass(frozen=True)
class InitData:
    user_id: int
    username: str | None
    language_code: str | None
    auth_date: int


def verify_init_data(init_data: str, bot_token: str, *, max_age: int = 86400) -> InitData | None:
    """Return the verified Telegram user, or None if the signature/age is bad."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True, keep_blank_values=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None

    # Freshness — reject a replayed/stale payload.
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if max_age > 0 and (time.time() - auth_date) > max_age:
        return None

    # `user` is a JSON blob; it is now trustworthy because the hash covered it.
    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        return None
    uid = user.get("id")
    if not isinstance(uid, int):
        return None
    return InitData(
        user_id=uid,
        username=user.get("username"),
        language_code=user.get("language_code"),
        auth_date=auth_date,
    )
