"""API key generation, hashing, validation, and reissue."""

from __future__ import annotations

import pytest

from app.core import security
from app.models.enums import ApiKeyStatus
from app.services import keys
from app.services.errors import InvalidKey, KeyDisabled
from tests.factories import make_user


def test_generate_and_hash_roundtrip():
    gen = security.generate_api_key()
    assert len(gen.prefix) == 8
    assert gen.raw.startswith(gen.prefix)
    assert security.hash_key(gen.raw) == gen.key_hash
    assert gen.key_hash != gen.raw  # only the hash is ever stored


async def test_validate_accepts_active_key(db):
    user = await make_user(db)
    _key, raw = await keys.issue(db, user.id)
    await db.commit()

    validated = await keys.validate(db, raw)
    assert validated.user_id == user.id
    assert validated.last_used_at is not None


async def test_validate_rejects_unknown_key(db):
    with pytest.raises(InvalidKey):
        await keys.validate(db, "definitely-not-a-real-key")


async def test_validate_rejects_disabled_key(db):
    user = await make_user(db)
    key, raw = await keys.issue(db, user.id)
    key.status = ApiKeyStatus.DISABLED
    await db.commit()

    with pytest.raises(KeyDisabled):
        await keys.validate(db, raw)


async def test_reissue_disables_old_key(db):
    user = await make_user(db)
    old_key, old_raw = await keys.issue(db, user.id)
    await db.commit()

    _new_key, new_raw = await keys.reissue(db, user.id)
    await db.commit()

    assert new_raw != old_raw
    # Old key no longer validates; new one does.
    with pytest.raises(KeyDisabled):
        await keys.validate(db, old_raw)
    assert (await keys.validate(db, new_raw)).user_id == user.id
