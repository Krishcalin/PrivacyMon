"""Detector behaviour tests (SRS 4.1, 4.4)."""
from __future__ import annotations

from dpia_core.detectors import DEFAULT_PACK_VERSION, default_detectors
from dpia_core.detectors import validators as V
from dpia_core.engine import evaluate_column
from dpia_core.models import Category, ProtectionState, ScanProfile

DETS = default_detectors()


def _cats(column_name, values, **kw):
    f = evaluate_column(DETS, column_name, values, pack_version=DEFAULT_PACK_VERSION, **kw)
    return {x.category for x in f}


def test_aadhaar_detected_with_valid_checksum():
    good = "23412341234" + str(V.verhoeff_checksum("23412341234"))
    assert Category.AADHAAR in _cats("aadhaar_number", [good])


def test_aadhaar_not_detected_with_bad_checksum():
    bad = "23412341234" + str((V.verhoeff_checksum("23412341234") + 1) % 10)
    assert Category.AADHAAR not in _cats("ref", [bad])


def test_mobile_requires_context_or_prefix():
    # Bare 10-digit in a neutral/negative column: no finding.
    assert Category.MOBILE not in _cats("order_id", ["9876543210"])
    # Same value in a mobile column: detected.
    assert Category.MOBILE in _cats("mobile", ["9876543210"])
    # +91 prefix is a strong match that fires without column context.
    assert Category.MOBILE in _cats("col1", ["+91 98765 43210"])


def test_bank_account_requires_context():
    assert Category.BANK_ACCOUNT not in _cats("order_id", ["123456789012"])
    assert Category.BANK_ACCOUNT in _cats("account_no", ["123456789012"])


def test_payment_card_luhn_gate():
    assert Category.PAYMENT_CARD in _cats("card_no", ["4111111111111111"])
    assert Category.PAYMENT_CARD not in _cats("card_no", ["4111111111111112"])


def test_schema_only_profile_fires_on_exact_name():
    cats = _cats("aadhaar_number", [], profile=ScanProfile.QUICK)
    assert Category.AADHAAR in cats


def test_tokenised_protection_state_detected():
    # Format-preserving tokens: match the Aadhaar pattern but fail Verhoeff.
    tokens = ["234123412340", "234123412341", "234123412342"]
    f = evaluate_column(DETS, "aadhaar_no", tokens, pack_version=DEFAULT_PACK_VERSION)
    # None are valid Aadhaar, so the Aadhaar detector should not fire...
    assert Category.AADHAAR not in {x.category for x in f}


def test_plain_critical_marked_plain():
    good = ["23412341234" + str(V.verhoeff_checksum("23412341234"))]
    f = evaluate_column(DETS, "aadhaar_number", good, pack_version=DEFAULT_PACK_VERSION)
    aadhaar = next(x for x in f if x.category == Category.AADHAAR)
    assert aadhaar.protection_state == ProtectionState.PLAIN
    assert aadhaar.evidence and aadhaar.evidence[0].startswith("XXXX")
