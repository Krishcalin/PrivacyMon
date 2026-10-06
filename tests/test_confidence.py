"""Confidence model and threshold bands (SRS 4.4)."""
from __future__ import annotations

import pytest

from dpia_core.detectors.base import compute_confidence
from dpia_core.models import ConfidenceLabel, confidence_label


def test_formula_matches_srs():
    # C = min(1, B + K_ctx + H*0.3 - N_ctx)
    assert compute_confidence(0.70, 0.25, 1.0, 0.0) == pytest.approx(1.0)
    assert compute_confidence(0.35, 0.0, 0.0, 0.0) == pytest.approx(0.35)
    assert compute_confidence(0.70, 0.15, 0.5, 0.0) == pytest.approx(0.70 + 0.15 + 0.15)


def test_negative_context_and_clamp():
    assert compute_confidence(0.35, 0.0, 1.0, 0.30) == pytest.approx(0.35)
    assert compute_confidence(0.35, 0.0, 0.0, 0.30) == pytest.approx(0.05)
    assert compute_confidence(0.40, 0.0, 0.0, 0.90) == 0.0  # clamped at 0


def test_threshold_bands():
    assert confidence_label(0.85) is ConfidenceLabel.LIKELY
    assert confidence_label(0.80) is ConfidenceLabel.LIKELY
    assert confidence_label(0.60) is ConfidenceLabel.NEEDS_REVIEW
    assert confidence_label(0.50) is ConfidenceLabel.NEEDS_REVIEW
    assert confidence_label(0.49) is ConfidenceLabel.HIDDEN
