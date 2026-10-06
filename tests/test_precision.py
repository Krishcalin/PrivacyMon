"""Detector precision / recall on the synthetic Indian PII fixture.

SRS acceptance criterion (13.1): detector pack v1 scores precision >= 0.95 and
recall >= 0.90 on the synthetic fixture.
"""
from __future__ import annotations

from dpia_core.detectors import DEFAULT_PACK_VERSION, default_detectors
from dpia_core.engine import evaluate_column, visible_findings
from fixtures.pii.samples import NEGATIVES, POSITIVES

DETS = default_detectors()


def _visible(col):
    findings = evaluate_column(
        DETS, col.column_name, col.values,
        data_type=col.data_type, pack_version=DEFAULT_PACK_VERSION,
    )
    return visible_findings(findings, 0.50)


def test_every_positive_is_detected():
    missed = []
    for col in POSITIVES:
        cats = {f.category for f in _visible(col)}
        if col.expected not in cats:
            missed.append((col.column_name, col.expected.value, sorted(c.value for c in cats)))
    assert not missed, f"missed positives: {missed}"


def test_no_false_positives_on_negatives():
    false_positives = []
    for col in NEGATIVES:
        for f in _visible(col):
            false_positives.append((col.column_name, f.category.value, f.evidence))
    assert not false_positives, f"false positives: {false_positives}"


def test_precision_and_recall_thresholds():
    tp = fn = 0
    for col in POSITIVES:
        cats = {f.category for f in _visible(col)}
        if col.expected in cats:
            tp += 1
        else:
            fn += 1
    fp = sum(len(_visible(col)) for col in NEGATIVES)

    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    assert recall >= 0.90, f"recall {recall:.3f}"
    assert precision >= 0.95, f"precision {precision:.3f} (fp={fp})"
