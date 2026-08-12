"""Expiry-reminder band logic (offline, pure)."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from app.services import reminders as r  # noqa: E402


def test_parse_days_sorts_dedups_and_drops_junk():
    assert r.parse_days("3,1") == [3, 1]
    assert r.parse_days("1,3,3, ,x,0,-2") == [3, 1]
    assert r.parse_days("") == []
    assert r.parse_days("7") == [7]


def test_bands_are_non_overlapping_descending():
    # remind when low < days_left <= high; bands must tile (no gaps/overlap) down to 0
    assert r.bands([3, 1]) == [(3, 1), (1, 0)]
    assert r.bands([7, 3, 1]) == [(7, 3), (3, 1), (1, 0)]
    assert r.bands([1]) == [(1, 0)]
    assert r.bands([2, 2]) == [(2, 0)]  # dedup


def test_is_enabled_requires_flag_and_days(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "expiry_reminders_enabled", True)
    monkeypatch.setattr(settings, "expiry_reminder_days", "3,1")
    assert r.is_enabled() is True
    monkeypatch.setattr(settings, "expiry_reminder_days", "")
    assert r.is_enabled() is False
    monkeypatch.setattr(settings, "expiry_reminder_days", "3")
    monkeypatch.setattr(settings, "expiry_reminders_enabled", False)
    assert r.is_enabled() is False
