"""Compile a user-defined detector (a stored row) into a runnable ``DetectorSpec``
(SRS FR-4.7). Custom detectors are created through the admin UI and persisted as rows
(id, category, tier, pattern, validator-name, context lists); this turns such a row into
the same kind of spec the built-in pack uses, so the engine treats custom and built-in
detectors identically.

Safety: a custom detector may carry a regex and may NAME one of the built-in validators,
but it can never supply executable code — the validator is resolved from a fixed registry
of vetted functions, so an admin cannot inject arbitrary callables.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import validators as V
from .base import DetectorSpec
from ..models import Category, DetectorKind, Tier

# The only validators a custom detector may reference, by name (SRS FR-4.7). Names are
# stable identifiers stored in ``detectors.validator``; anything else is rejected.
VALIDATOR_REGISTRY: dict[str, Callable[[str], bool]] = {
    "aadhaar_valid": V.aadhaar_valid,
    "aadhaar_vid_valid": V.aadhaar_vid_valid,
    "pan_valid": V.pan_valid,
    "payment_card_valid": V.payment_card_valid,
    "luhn_validate": V.luhn_validate,
    "gstin_valid": V.gstin_valid,
    "ifsc_valid": V.ifsc_valid,
    "driving_licence_valid": V.driving_licence_valid,
    "vehicle_reg_valid": V.vehicle_reg_valid,
    "pin_code_valid": V.pin_code_valid,
    "epf_uan_valid": V.epf_uan_valid,
    "upi_valid": V.upi_valid,
    "email_valid": V.email_valid,
    "dob_valid": V.dob_valid,
}


class DetectorCompileError(ValueError):
    """A stored detector row could not be compiled into a usable spec."""


def validator_names() -> list[str]:
    return sorted(VALIDATOR_REGISTRY)


def _coerce_pattern(pattern: str | None) -> "re.Pattern | None":
    if not pattern:
        return None
    try:
        return re.compile(pattern)
    except re.error as e:
        raise DetectorCompileError(f"invalid regex: {e}") from e


def spec_from_row(row: Any) -> DetectorSpec:
    """Build a ``DetectorSpec`` from a stored detector (an object or mapping with
    ``id``/``category``/``tier``/``pattern``/``validator``/context lists).

    The kind is inferred: a validator makes it PATTERN_VALIDATOR; a pattern alone makes
    it PATTERN; neither (a pure name/keyword match via context) makes it DICTIONARY.
    """
    def get(key: str, default=None):
        if isinstance(row, dict):
            return row.get(key, default)
        return getattr(row, key, default)

    raw_id = get("id")
    det_id = f"custom.{raw_id}" if raw_id is not None else "custom.unnamed"

    category = get("category")
    category = category if isinstance(category, Category) else Category(str(category))
    tier = get("tier")
    tier = tier if isinstance(tier, Tier) else Tier(str(tier))

    pattern = _coerce_pattern(get("pattern"))

    validator_name = get("validator")
    validator = None
    if validator_name:
        validator = VALIDATOR_REGISTRY.get(str(validator_name))
        if validator is None:
            raise DetectorCompileError(f"unknown validator: {validator_name!r}")

    if validator is not None:
        kind = DetectorKind.PATTERN_VALIDATOR
    elif pattern is not None:
        kind = DetectorKind.PATTERN
    else:
        kind = DetectorKind.DICTIONARY

    ctx_pos = list(get("context_positive", []) or [])
    ctx_neg = list(get("context_negative", []) or [])

    # A dictionary (name-only) detector needs positive context to fire at all.
    if kind == DetectorKind.DICTIONARY and not ctx_pos:
        raise DetectorCompileError(
            "a detector with no pattern and no validator must list context_positive "
            "column-name keywords")

    return DetectorSpec(
        id=det_id, category=category, tier=tier, kind=kind,
        context_positive=ctx_pos, context_negative=ctx_neg,
        pattern=pattern, validator=validator,
        requires_context=bool(get("requires_context", kind == DetectorKind.DICTIONARY)),
        description=str(get("description", "") or ""),
    )
