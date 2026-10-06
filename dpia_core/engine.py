"""Detection engine: turn sampled column values or free text into findings.

Implements the per-column aggregation, confidence scoring, protection-state
inference, children-from-DOB promotion and the co-occurrence pass described in
SRS sections 4.3-4.5 and 7.2.
"""
from __future__ import annotations

from collections import defaultdict

from .detectors import validators as V
from .detectors.base import DetectorSpec, K_CTX_EXACT, compute_confidence
from .detectors.dictionary import scan_column_metadata
from .models import (
    Category,
    ConfidenceLabel,
    DetectorKind,
    Finding,
    Locator,
    ProtectionState,
    ScanProfile,
    Tier,
    confidence_label,
    tier_uplift,
)
from .masking import mask
from .protection import infer_protection_state

_CHILD_AGE = 18


def evaluate_column(
    detectors: list[DetectorSpec],
    column_name: str | None,
    sample_values: list,
    *,
    data_type: str | None = None,
    schema: str | None = None,
    table: str | None = None,
    profile: ScanProfile = ScanProfile.STANDARD,
    pack_version: str = "",
) -> list[Finding]:
    """Evaluate one column and return its findings (one per firing detector)."""
    loc = Locator(kind="database", schema=schema, table=table, column=column_name)
    findings: list[Finding] = []

    # 1. Column-metadata detectors (biometric, photo / scanned ID).
    for cat, tier in scan_column_metadata(column_name, data_type):
        findings.append(Finding(
            category=cat, tier=tier,
            detector_id=f"metadata.{cat.value}", detector_kind=DetectorKind.DICTIONARY,
            confidence=min(1.0, 0.40 + K_CTX_EXACT), hit_rate=0.0, locator=loc,
            evidence=[], protection_state=ProtectionState.UNKNOWN,
            base_score=0.40, context_positive=True, pack_version=pack_version,
        ))

    values = [v for v in sample_values if v is not None and str(v).strip()]
    n = len(values)
    schema_only = profile == ScanProfile.QUICK or n == 0

    child_hit_rate = 0.0
    dob_confidence = 0.0

    for det in detectors:
        ctx = det.context_bonus(column_name)
        neg = det.negative_bonus(column_name)

        if schema_only:
            # Name-only detection: fire only on an exact column-name match.
            if ctx >= K_CTX_EXACT:
                conf = compute_confidence(det.base_score, ctx, 0.0, neg)
                if conf > 0:
                    findings.append(Finding(
                        category=det.category, tier=det.tier, detector_id=det.id,
                        detector_kind=det.kind, confidence=conf, hit_rate=0.0,
                        locator=loc, evidence=[], protection_state=ProtectionState.UNKNOWN,
                        base_score=det.base_score, context_positive=True,
                        context_negative=neg > 0, pack_version=pack_version,
                    ))
            continue

        matches = [hit for v in values if (hit := det.match_value(str(v))) is not None]
        if not matches:
            continue
        strong = any(det.is_strong(m) for m in matches)
        if det.requires_context and ctx == 0 and not strong:
            continue

        hit_rate = len(matches) / n
        conf = compute_confidence(det.base_score, ctx, hit_rate, neg)
        prot = infer_protection_state(values, det.pattern, det.validator)
        evidence = [mask(det.category, m) for m in matches[:3]]
        findings.append(Finding(
            category=det.category, tier=det.tier, detector_id=det.id,
            detector_kind=det.kind, confidence=conf, hit_rate=hit_rate, locator=loc,
            evidence=evidence, protection_state=prot, base_score=det.base_score,
            context_positive=ctx > 0, context_negative=neg > 0, pack_version=pack_version,
        ))

        # Children's data via DOB implying age < 18 (SRS 4.2 / 5.1 S.9).
        if det.category == Category.DOB:
            under = [m for m in matches if (a := V.age_from_dob(m)) is not None and a < _CHILD_AGE]
            if under:
                child_hit_rate = len(under) / n
                dob_confidence = conf

    if child_hit_rate > 0 and not any(f.category == Category.CHILDREN_DATA for f in findings):
        findings.append(Finding(
            category=Category.CHILDREN_DATA, tier=Tier.CRITICAL,
            detector_id="children_data.from_dob", detector_kind=DetectorKind.PATTERN_VALIDATOR,
            confidence=dob_confidence, hit_rate=child_hit_rate, locator=loc,
            evidence=["dob implies age < 18"], protection_state=ProtectionState.UNKNOWN,
            base_score=0.70, context_positive=True, pack_version=pack_version,
        ))

    return findings


def evaluate_text(
    detectors: list[DetectorSpec],
    text: str,
    *,
    path: str | None = None,
    line: int | None = None,
    pack_version: str = "",
) -> list[Finding]:
    """Scan a free-text blob (e.g. a source file or string literal).

    Only detectors that do not require column context fire here, since a text
    blob carries no column name. Each firing detector yields one finding.
    """
    loc = Locator(kind="file", path=path, line=line)
    findings: list[Finding] = []
    for det in detectors:
        if det.requires_context:
            continue
        matches = list(det.iter_matches(text))
        if not matches:
            continue
        conf = compute_confidence(det.base_score, 0.0, 1.0, 0.0)
        evidence = [mask(det.category, m) for m in matches[:3]]
        findings.append(Finding(
            category=det.category, tier=det.tier, detector_id=det.id,
            detector_kind=det.kind, confidence=conf, hit_rate=1.0, locator=loc,
            evidence=evidence, protection_state=ProtectionState.PLAIN,
            base_score=det.base_score, pack_version=pack_version,
        ))
    return findings


def apply_cooccurrence(findings: list[Finding]) -> list[Finding]:
    """Flag combined-identity records and uplift one tier (SRS 4.3).

    A unit (table or file) holding identifiers from two or more categories is a
    combined identity record; every finding in it is raised one tier.
    """
    by_unit: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_unit[f.locator.unit_key()].append(f)
    for group in by_unit.values():
        categories = {f.category for f in group}
        if len(categories) >= 2:
            for f in group:
                if not f.combined_identity:
                    f.combined_identity = True
                    f.tier = tier_uplift(f.tier, 1)
    return findings


def visible_findings(
    findings: list[Finding],
    review_threshold: float = 0.50,
) -> list[Finding]:
    """Findings at or above the 'needs review' threshold (SRS 4.4)."""
    return [f for f in findings if f.confidence >= review_threshold]


def summarise(findings: list[Finding]) -> dict:
    """Aggregate counts by category and tier, for inventory and risk."""
    by_category: dict[str, int] = defaultdict(int)
    by_tier: dict[str, int] = defaultdict(int)
    by_label: dict[str, int] = defaultdict(int)
    for f in findings:
        by_category[f.category.value] += 1
        by_tier[f.tier.value] += 1
        by_label[confidence_label(f.confidence).value] += 1
    return {
        "total": len(findings),
        "by_category": dict(by_category),
        "by_tier": dict(by_tier),
        "by_confidence": dict(by_label),
        "combined_identity_units": len({
            f.locator.unit_key() for f in findings if f.combined_identity
        }),
    }
