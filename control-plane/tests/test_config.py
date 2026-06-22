"""ADMIN_IDS env parsing — regression for the `set_type` startup crash.

Previously `admin_ids: set[int]` made pydantic-settings JSON-decode the env value
before the validator, so a bare id (`1966832731`) crashed and a comma list raised
SettingsError. These tests pin the forgiving behavior.
"""

from __future__ import annotations

from app.core.config import Settings


def _settings(monkeypatch, value=None) -> Settings:
    if value is None:
        monkeypatch.delenv("ADMIN_IDS", raising=False)
    else:
        monkeypatch.setenv("ADMIN_IDS", value)
    # _env_file=None isolates from any local .env so we test the env value only.
    return Settings(_env_file=None)


def test_single_admin_id(monkeypatch):
    assert _settings(monkeypatch, "1966832731").admin_ids == {1966832731}


def test_comma_separated_admin_ids(monkeypatch):
    assert _settings(monkeypatch, "111,222").admin_ids == {111, 222}


def test_bracketed_admin_ids(monkeypatch):
    assert _settings(monkeypatch, "[111, 222]").admin_ids == {111, 222}


def test_empty_admin_ids(monkeypatch):
    assert _settings(monkeypatch, "").admin_ids == set()


def test_unset_admin_ids(monkeypatch):
    assert _settings(monkeypatch).admin_ids == set()
