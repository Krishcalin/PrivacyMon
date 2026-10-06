"""Evidence masking (SRS 8.5)."""
from __future__ import annotations

from dpia_core.masking import mask, mask_shape
from dpia_core.models import Category


def test_aadhaar_keeps_last_four():
    assert mask(Category.AADHAAR, "2341 2341 2345") == "XXXX XXXX 2345"


def test_pan_first_three_last_one():
    assert mask(Category.PAN, "ABCPK1234L") == "ABC****L"


def test_mobile_and_card_last_four():
    assert mask(Category.MOBILE, "+91 98765 43210") == "********3210"
    assert mask(Category.PAYMENT_CARD, "4111111111111111") == "**** **** **** 1111"


def test_email_first_char_and_domain():
    assert mask(Category.EMAIL, "ananya.roy@example.com") == "a***@example.com"


def test_shape_mask():
    assert mask_shape("Ananya Roy") == "Xxxxxx Xxx"
    assert mask_shape("12, Park St") == "nn, Xxxx Xx"


def test_no_raw_value_leaks():
    raw = "2341 2341 2345"
    masked = mask(Category.AADHAAR, raw)
    assert "2341 2341" not in masked  # leading digits never survive
