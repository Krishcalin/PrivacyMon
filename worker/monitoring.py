"""Continuous-monitoring core: cron matching + inventory change detection (SRS FR-3.1,
FR-4.x). Pure and dependency-free so it is unit-testable without a database or broker.

A scan is scheduled by a 5-field cron expression on a data source. ``cron_due`` answers
"should this fire at minute T?" with a small, standard cron evaluator (minute, hour,
day-of-month, month, day-of-week; ``*``, ``*/step``, ``a-b`` ranges and ``a,b`` lists).

After a scan, ``diff_inventory`` compares the new per-category inventory to the previous
scan's and classifies the change: new categories, categories that gained a higher tier,
and categories with materially more locations. ``is_material`` decides whether the change
warrants a re-assessment flag and a notification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

_TIER_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


# ── cron ──────────────────────────────────────────────────────────────────────
def _field_matches(expr: str, value: int, lo: int, hi: int) -> bool:
    """Match one cron field (already split on commas upstream is not needed — we handle
    lists here). Supports ``*``, ``*/step``, ``a-b``, ``a-b/step`` and plain integers."""
    for part in expr.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
        else:
            base = part
        if base in ("*", ""):
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = int(a), int(b)
        else:
            n = int(base)
            start, end = n, n
        if start > end:
            continue
        for candidate in range(start, end + 1, step):
            if candidate == value:
                return True
    return False


def cron_due(expr: str | None, when: datetime) -> bool:
    """True when a 5-field cron expression fires at ``when`` (minute granularity).

    Fields: minute hour day-of-month month day-of-week (0 or 7 = Sunday). An invalid or
    empty expression never fires. Day-of-month and day-of-week both default (``*``) to a
    match; when both are restricted, standard cron ORs them, which we follow."""
    if not expr or not expr.strip():
        return False
    parts = expr.split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    try:
        if not _field_matches(minute, when.minute, 0, 59):
            return False
        if not _field_matches(hour, when.hour, 0, 23):
            return False
        if not _field_matches(month, when.month, 1, 12):
            return False
        # cron weekday: Monday=1..Sunday=0/7; python weekday() Monday=0..Sunday=6
        py_dow = when.weekday()
        cron_dow = (py_dow + 1) % 7  # Mon=1..Sat=6,Sun=0
        dom_restricted = dom.strip() != "*"
        dow_restricted = dow.strip() != "*"
        dom_hit = _field_matches(dom, when.day, 1, 31)
        dow_hit = _field_matches(dow, cron_dow, 0, 7) or _field_matches(dow, 7 if cron_dow == 0 else cron_dow, 0, 7)
        if dom_restricted and dow_restricted:
            return dom_hit or dow_hit
        if dom_restricted:
            return dom_hit
        if dow_restricted:
            return dow_hit
        return True
    except (ValueError, TypeError):
        return False


# ── inventory change detection ────────────────────────────────────────────────
@dataclass
class InventoryDelta:
    """Classified difference between two scans' inventories (per category)."""

    new_categories: list[str] = field(default_factory=list)       # category seen for the first time
    escalated: list[dict] = field(default_factory=list)           # {category, from, to} tier rose
    grew: list[dict] = field(default_factory=list)                # {category, from, to} locations rose
    removed_categories: list[str] = field(default_factory=list)   # category no longer found
    new_critical: list[str] = field(default_factory=list)         # category now at critical/high tier (new or escalated)

    @property
    def any_change(self) -> bool:
        return bool(self.new_categories or self.escalated or self.grew
                    or self.removed_categories)

    def as_dict(self) -> dict:
        return {
            "new_categories": self.new_categories,
            "escalated": self.escalated,
            "grew": self.grew,
            "removed_categories": self.removed_categories,
            "new_critical": self.new_critical,
        }


def _norm(inv: dict) -> dict[str, dict]:
    """Normalise an inventory snapshot to {category: {tier, locations_count}}.

    Accepts either the live rebuild shape ({cat: {tier(enum|str), locations_count}}) or a
    stored snapshot ({cat: {tier: str, locations_count: int}})."""
    out: dict[str, dict] = {}
    for cat, v in (inv or {}).items():
        tier = v.get("tier")
        tier = getattr(tier, "value", tier)
        out[str(cat)] = {
            "tier": str(tier) if tier is not None else "low",
            "locations_count": int(v.get("locations_count", 0) or 0),
        }
    return out


def diff_inventory(previous: dict, current: dict, *, grow_factor: float = 1.5,
                   grow_min: int = 5) -> InventoryDelta:
    """Classify the change from ``previous`` to ``current`` inventory.

    A category "grew" when its location count rose by at least ``grow_factor`` AND by at
    least ``grow_min`` absolute (so a 1→2 jiggle is ignored but a real spread is caught).
    ``new_critical`` collects categories that are now high/critical and were not before.
    """
    prev, cur = _norm(previous), _norm(current)
    delta = InventoryDelta()
    for cat, c in cur.items():
        p = prev.get(cat)
        cur_rank = _TIER_RANK.get(c["tier"], 0)
        if p is None:
            delta.new_categories.append(cat)
            if cur_rank >= _TIER_RANK["high"]:
                delta.new_critical.append(cat)
            continue
        prev_rank = _TIER_RANK.get(p["tier"], 0)
        if cur_rank > prev_rank:
            delta.escalated.append({"category": cat, "from": p["tier"], "to": c["tier"]})
            if cur_rank >= _TIER_RANK["high"] and prev_rank < _TIER_RANK["high"]:
                delta.new_critical.append(cat)
        if (c["locations_count"] >= p["locations_count"] * grow_factor
                and c["locations_count"] - p["locations_count"] >= grow_min):
            delta.grew.append({"category": cat, "from": p["locations_count"],
                               "to": c["locations_count"]})
    for cat in prev:
        if cat not in cur:
            delta.removed_categories.append(cat)
    return delta


def is_material(delta: InventoryDelta) -> bool:
    """A change warrants a re-assessment flag + notification when a new category appears,
    a tier escalates, a new high/critical category shows up, or a category grows a lot.
    Removing a category alone is noted but not treated as material (it lowers risk)."""
    return bool(delta.new_categories or delta.escalated or delta.new_critical or delta.grew)
