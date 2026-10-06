"""Detector specification and the confidence model (SRS sections 4.1, 4.4).

A detector is a declarative :class:`DetectorSpec`: a pattern (what a value looks
like), a validator (checksum or structural test), positive/negative context
keywords (column, field and variable names) and a sensitivity tier. The
confidence model combines these into one score per finding.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..models import BASE_SCORE, Category, DetectorKind, Tier

# Confidence weights (SRS section 4.4).
K_CTX_EXACT = 0.25
K_CTX_PARTIAL = 0.15
N_CTX = 0.30
H_WEIGHT = 0.30

# Negative context tokens shared by numeric detectors that collide with
# business identifiers (SRS section 4.4).
COMMON_NEGATIVE = ["order_id", "order_no", "invoice_no", "invoice", "txn_ref",
                   "transaction", "seq", "sequence", "ref_no", "receipt"]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t}


@dataclass
class DetectorSpec:
    """One detector in a pack."""

    id: str
    category: Category
    tier: Tier
    kind: DetectorKind
    context_positive: list[str] = field(default_factory=list)
    context_negative: list[str] = field(default_factory=list)
    pattern: re.Pattern | None = None
    validator: Callable[[str], bool] | None = None
    # Value-level matcher for dictionary detectors (no regex).
    value_matcher: Callable[[str], bool] | None = None
    # A value that is "strong" fires without positive column context
    # (e.g. a mobile number written with a +91 prefix, SRS 4.1).
    strong_match: Callable[[str], bool] | None = None
    # When True the detector does not fire on pattern alone: it needs positive
    # column/field context or a strong match (SRS 4.1 "context required").
    requires_context: bool = False
    description: str = ""

    @property
    def base_score(self) -> float:
        return BASE_SCORE[self.kind]

    # -- matching -----------------------------------------------------------
    def match_value(self, value: str) -> str | None:
        """Return the matched substring if ``value`` matches, else None."""
        if self.pattern is not None:
            m = self.pattern.search(value)
            if not m:
                return None
            hit = m.group()
            if self.validator is not None and not self.validator(hit):
                return None
            return hit
        if self.value_matcher is not None:
            return value if self.value_matcher(value) else None
        return None

    def iter_matches(self, text: str):
        """Yield every validated match in ``text`` (for free-text scanning)."""
        if self.pattern is None:
            if self.value_matcher is not None and self.value_matcher(text):
                yield text
            return
        for m in self.pattern.finditer(text):
            hit = m.group()
            if self.validator is None or self.validator(hit):
                yield hit

    def is_strong(self, value: str) -> bool:
        return bool(self.strong_match and self.strong_match(value))

    # -- context ------------------------------------------------------------
    def context_bonus(self, column_name: str | None) -> float:
        """K_ctx: +0.25 exact token/name match, +0.15 partial (SRS 4.4)."""
        if not column_name:
            return 0.0
        toks = _tokens(column_name)
        norm = _norm(column_name)
        for kw in self.context_positive:
            k = kw.lower()
            if k in toks or norm == _norm(k):
                return K_CTX_EXACT
        for kw in self.context_positive:
            if _norm(kw) and _norm(kw) in norm:
                return K_CTX_PARTIAL
        return 0.0

    def negative_bonus(self, column_name: str | None) -> float:
        """N_ctx: -0.30 when the name suggests a different meaning (SRS 4.4)."""
        if not column_name:
            return 0.0
        norm = _norm(column_name)
        for kw in self.context_negative:
            if _norm(kw) and _norm(kw) in norm:
                return N_CTX
        return 0.0


def compute_confidence(
    base: float,
    context_bonus: float,
    hit_rate: float,
    negative_bonus: float,
) -> float:
    """C = min(1, B + K_ctx + H*0.3 - N_ctx), clamped to [0, 1] (SRS 4.4)."""
    c = base + context_bonus + hit_rate * H_WEIGHT - negative_bonus
    return max(0.0, min(1.0, c))
