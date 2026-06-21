"""API key lifecycle: issue, validate, reissue.

The raw key is returned only at issue time; everything else works off the
sha256 hash. Validation never trusts anything client-side beyond the key string,
which is hashed and matched against storage.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models.api_key import ApiKey
from app.models.enums import ApiKeyStatus
from app.services.audit import record_audit
from app.services.errors import InvalidKey, KeyDisabled


async def issue(db: AsyncSession, user_id: int) -> tuple[ApiKey, str]:
    """Disable any existing active keys for the user, then mint a fresh one."""
    await db.execute(
        update(ApiKey)
        .where(ApiKey.user_id == user_id, ApiKey.status == ApiKeyStatus.ACTIVE)
        .values(status=ApiKeyStatus.DISABLED)
    )
    gen = security.generate_api_key()
    key = ApiKey(
        user_id=user_id,
        key_hash=gen.key_hash,
        prefix=gen.prefix,
        status=ApiKeyStatus.ACTIVE,
    )
    db.add(key)
    await db.flush()
    await record_audit(
        db, actor="system", action="key_issued", target=str(key.id),
        meta={"user_id": user_id, "prefix": gen.prefix},
    )
    return key, gen.raw


async def reissue(db: AsyncSession, user_id: int) -> tuple[ApiKey, str]:
    """Reissue == issue (old keys are disabled inside `issue`)."""
    key, raw = await issue(db, user_id)
    await record_audit(
        db, actor=f"user:{user_id}", action="key_reissued", target=str(key.id),
        meta={"user_id": user_id},
    )
    return key, raw


async def validate(db: AsyncSession, raw_key: str) -> ApiKey:
    """Look up by hash. Raises InvalidKey / KeyDisabled. Touches last_used_at."""
    key_hash = security.hash_key(raw_key)
    key = await db.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
    if key is None:
        raise InvalidKey()
    if key.status != ApiKeyStatus.ACTIVE:
        raise KeyDisabled()
    key.last_used_at = datetime.now(UTC)
    return key


async def get_active_key(db: AsyncSession, user_id: int) -> ApiKey | None:
    return await db.scalar(
        select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.status == ApiKeyStatus.ACTIVE)
    )
