"""Evidence masking (SRS section 8.5).

Evidence is masked by the detector *before it leaves worker memory*. The raw
sampled value is never persisted. Each category keeps only the minimum needed
to prove a finding to a reviewer.
"""
from __future__ import annotations

import re

from .models import Category


def _only_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def mask_keep_last(value: str, keep: int) -> str:
    digits = _only_digits(value)
    if len(digits) <= keep:
        return "*" * len(digits)
    return "*" * (len(digits) - keep) + digits[-keep:]


def mask_aadhaar(value: str) -> str:
    # Keep the last 4 digits, grouped 4-4-4.
    digits = _only_digits(value)[-12:]
    tail = digits[-4:] if len(digits) >= 4 else digits
    return f"XXXX XXXX {tail}"


def mask_pan(value: str) -> str:
    v = value.strip().upper()
    if len(v) < 10:
        return "*" * len(v)
    return f"{v[:3]}****{v[9]}"


def mask_mobile(value: str) -> str:
    return mask_keep_last(value, 4)


def mask_card(value: str) -> str:
    return "**** **** **** " + _only_digits(value)[-4:]


def mask_email(value: str) -> str:
    v = value.strip()
    local, _, domain = v.partition("@")
    if not local:
        return "***"
    return f"{local[0]}***@{domain}" if domain else f"{local[0]}***"


def mask_upi(value: str) -> str:
    handle, _, psp = value.strip().partition("@")
    first = handle[0] if handle else "*"
    return f"{first}***@{psp}" if psp else f"{first}***"


def mask_shape(value: str) -> str:
    """Replace a free-text value (name, address) with its shape.

    "Ananya Roy"            -> "Xxxxxx Xxx"
    "12, Park Street 700016" -> "nn, Xxxx Xxxxxx nnnnnn"
    """
    out: list[str] = []
    for ch in value.strip():
        if ch.isdigit():
            out.append("n")
        elif ch.isupper():
            out.append("X")
        elif ch.islower():
            out.append("x")
        else:
            out.append(ch)
    return "".join(out)


_MASKERS = {
    Category.AADHAAR: mask_aadhaar,
    Category.AADHAAR_VID: mask_aadhaar,
    Category.PAN: mask_pan,
    Category.MOBILE: mask_mobile,
    Category.PAYMENT_CARD: mask_card,
    Category.EMAIL: mask_email,
    Category.UPI_ID: mask_upi,
    Category.PERSON_NAME: mask_shape,
    Category.ADDRESS: mask_shape,
}


def mask(category: Category, value: str) -> str:
    """Mask ``value`` for a finding of ``category``."""
    masker = _MASKERS.get(category)
    if masker is not None:
        return masker(value)
    # Default: identifiers keep the last 4, free text keeps its shape.
    if any(c.isdigit() for c in value) and len(_only_digits(value)) >= 4:
        return mask_keep_last(value, 4)
    return mask_shape(value)
