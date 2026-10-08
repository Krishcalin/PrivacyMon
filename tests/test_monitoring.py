"""Continuous-monitoring core: cron matching + inventory change detection (SRS FR-3.1,
FR-4.x). Pure and DB-free — the live scheduler/notification paths are exercised by the
Docker validation.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from worker.monitoring import cron_due, diff_inventory, is_material


# ── cron ──────────────────────────────────────────────────────────────────────
def test_cron_every_minute():
    assert cron_due("* * * * *", datetime(2026, 10, 8, 3, 14))


def test_cron_specific_minute_hour():
    assert cron_due("30 2 * * *", datetime(2026, 10, 8, 2, 30))
    assert not cron_due("30 2 * * *", datetime(2026, 10, 8, 2, 31))
    assert not cron_due("30 2 * * *", datetime(2026, 10, 8, 3, 30))


def test_cron_step_and_range():
    assert cron_due("*/15 * * * *", datetime(2026, 10, 8, 9, 0))
    assert cron_due("*/15 * * * *", datetime(2026, 10, 8, 9, 45))
    assert not cron_due("*/15 * * * *", datetime(2026, 10, 8, 9, 7))
    assert cron_due("0 9-17 * * *", datetime(2026, 10, 8, 13, 0))
    assert not cron_due("0 9-17 * * *", datetime(2026, 10, 8, 18, 0))


def test_cron_list():
    assert cron_due("0 0,12 * * *", datetime(2026, 10, 8, 12, 0))
    assert not cron_due("0 0,12 * * *", datetime(2026, 10, 8, 6, 0))


def test_cron_weekday():
    # 2026-10-08 is a Thursday (cron dow 4).
    assert cron_due("0 9 * * 4", datetime(2026, 10, 8, 9, 0))
    assert not cron_due("0 9 * * 1", datetime(2026, 10, 8, 9, 0))
    # Sunday as 0 and as 7.
    assert cron_due("0 9 * * 0", datetime(2026, 10, 11, 9, 0))  # Sunday
    assert cron_due("0 9 * * 7", datetime(2026, 10, 11, 9, 0))


def test_cron_invalid_or_empty_never_fires():
    for bad in (None, "", "   ", "* * *", "nope", "60 * * * *"):
        assert not cron_due(bad, datetime(2026, 10, 8, 3, 14))


# ── inventory diff ────────────────────────────────────────────────────────────
def _inv(**cats):
    return {c: {"tier": t, "locations_count": n} for c, (t, n) in cats.items()}


def test_diff_new_category_is_material():
    prev = _inv(email=("medium", 3))
    cur = _inv(email=("medium", 3), aadhaar=("critical", 2))
    d = diff_inventory(prev, cur)
    assert d.new_categories == ["aadhaar"]
    assert "aadhaar" in d.new_critical
    assert is_material(d)


def test_diff_tier_escalation_is_material():
    prev = _inv(pan=("medium", 2))
    cur = _inv(pan=("critical", 2))
    d = diff_inventory(prev, cur)
    assert d.escalated == [{"category": "pan", "from": "medium", "to": "critical"}]
    assert "pan" in d.new_critical
    assert is_material(d)


def test_diff_growth_requires_factor_and_absolute():
    # 2 -> 3 is a 1.5x factor but only +1 absolute (< grow_min) — not material.
    assert not is_material(diff_inventory(_inv(email=("low", 2)), _inv(email=("low", 3))))
    # 4 -> 12 is 3x and +8 absolute — material.
    d = diff_inventory(_inv(email=("low", 4)), _inv(email=("low", 12)))
    assert d.grew == [{"category": "email", "from": 4, "to": 12}]
    assert is_material(d)


def test_diff_removed_category_noted_but_not_material():
    d = diff_inventory(_inv(email=("low", 3), pan=("high", 1)), _inv(email=("low", 3)))
    assert d.removed_categories == ["pan"]
    assert not is_material(d)


def test_diff_no_change():
    inv = _inv(email=("low", 3), pan=("high", 2))
    d = diff_inventory(inv, inv)
    assert not d.any_change
    assert not is_material(d)


def test_diff_accepts_enum_like_tier():
    class _T:
        value = "critical"
    prev = {"pan": {"tier": "low", "locations_count": 1}}
    cur = {"pan": {"tier": _T(), "locations_count": 1}}
    d = diff_inventory(prev, cur)
    assert d.escalated and d.escalated[0]["to"] == "critical"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
