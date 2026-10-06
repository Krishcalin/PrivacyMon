"""Co-occurrence tier uplift and combined-identity flag (SRS 4.3)."""
from __future__ import annotations

from dpia_core.engine import apply_cooccurrence
from dpia_core.models import (
    Category,
    DetectorKind,
    Finding,
    Locator,
    Tier,
)


def _finding(category, tier, table):
    return Finding(
        category=category, tier=tier, detector_id="t", detector_kind=DetectorKind.PATTERN,
        confidence=0.9, hit_rate=1.0, locator=Locator(kind="database", table=table),
    )


def test_two_categories_same_table_uplift():
    findings = [
        _finding(Category.EMAIL, Tier.MEDIUM, "customers"),
        _finding(Category.MOBILE, Tier.MEDIUM, "customers"),
    ]
    apply_cooccurrence(findings)
    assert all(f.combined_identity for f in findings)
    assert all(f.tier is Tier.HIGH for f in findings)  # Medium -> High


def test_single_category_not_flagged():
    findings = [
        _finding(Category.EMAIL, Tier.MEDIUM, "logins"),
        _finding(Category.EMAIL, Tier.MEDIUM, "logins"),
    ]
    apply_cooccurrence(findings)
    assert not any(f.combined_identity for f in findings)
    assert all(f.tier is Tier.MEDIUM for f in findings)


def test_uplift_caps_at_critical():
    findings = [
        _finding(Category.AADHAAR, Tier.CRITICAL, "kyc"),
        _finding(Category.PAN, Tier.HIGH, "kyc"),
    ]
    apply_cooccurrence(findings)
    aadhaar = next(f for f in findings if f.category is Category.AADHAAR)
    assert aadhaar.tier is Tier.CRITICAL  # already critical, stays critical


def test_idempotent():
    findings = [
        _finding(Category.EMAIL, Tier.LOW, "t"),
        _finding(Category.MOBILE, Tier.LOW, "t"),
    ]
    apply_cooccurrence(findings)
    apply_cooccurrence(findings)  # second pass must not double-uplift
    assert all(f.tier is Tier.MEDIUM for f in findings)
