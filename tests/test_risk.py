"""Risk engine (SRS 5.3) — matches a hand-computed test case."""
from __future__ import annotations

import pytest

from dpia_core.controls import effectiveness_question_keys
from dpia_core.risk import (
    CategoryExposure,
    ExposureInputs,
    RiskBand,
    compute_risk,
    control_effectiveness,
    exposure_multiplier,
    volume_band,
)
from dpia_core.models import Tier


def test_volume_bands():
    assert volume_band(500) == 1
    assert volume_band(5_000) == 2
    assert volume_band(50_000) == 3
    assert volume_band(500_000) == 4
    assert volume_band(5_000_000) == 5


def test_exposure_multiplier():
    e = ExposureInputs(internet_facing=True, external_users=True, plain_high_or_critical=True)
    assert exposure_multiplier(e) == pytest.approx(1.5 * 1.3 * 1.5)  # 2.925


def test_control_effectiveness_weighting():
    keys = effectiveness_question_keys()
    assert control_effectiveness({k: "yes" for k in keys}) == pytest.approx(0.8)
    assert control_effectiveness({k: "no" for k in keys}) == 0.0
    # 'na' answers are excluded from the denominator.
    assert control_effectiveness({keys[0]: "na", keys[1]: "yes"}) == pytest.approx(0.8)


def test_hand_computed_case():
    # Aadhaar (Critical, 50k rows) + Mobile (Medium, 50k rows), internet-facing,
    # external users, plain critical data, all controls 'yes'.
    categories = [
        CategoryExposure(Tier.CRITICAL, 50_000),
        CategoryExposure(Tier.MEDIUM, 50_000),
    ]
    exposure = ExposureInputs(
        internet_facing=True, external_users=True, plain_high_or_critical=True,
    )
    answers = {k: "yes" for k in effectiveness_question_keys()}
    r = compute_risk(categories, exposure, answers)

    # inherent = (8*3 + 2*3) * 2.925 = 30 * 2.925 = 87.75
    assert r.exposure_multiplier == pytest.approx(2.925)
    assert r.inherent == pytest.approx(87.75)
    assert r.eta == pytest.approx(0.8)
    assert r.residual == pytest.approx(17.55)  # 87.75 * 0.2
    assert r.inherent_band is RiskBand.VERY_HIGH
    assert r.residual_band is RiskBand.MEDIUM
    assert r.gaps == []


def test_gaps_listed_for_no_and_partial():
    categories = [CategoryExposure(Tier.HIGH, 2_000)]
    exposure = ExposureInputs()
    answers = {"E1": "no", "E2": "partial", "H1": "yes"}
    r = compute_risk(categories, exposure, answers)
    assert "E1" in r.gaps and "E2" in r.gaps
    assert "H1" not in r.gaps
