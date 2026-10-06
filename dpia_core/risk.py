"""Risk engine (SRS section 5.3).

Inherent risk is computed from the inventory; residual risk applies the control
effectiveness derived from questionnaire answers.

    R_inherent = sum over categories of  W_c * V_c * E_app
    R_residual = R_inherent * (1 - eta_controls)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .controls import effectiveness_question_keys
from .models import TIER_WEIGHT, Tier


class RiskBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# Default residual-score band thresholds (configurable, SRS 5.3).
DEFAULT_BANDS = (
    (RiskBand.LOW, 10.0),
    (RiskBand.MEDIUM, 40.0),
    (RiskBand.HIGH, 80.0),
    (RiskBand.VERY_HIGH, float("inf")),
)


def volume_band(rows: int) -> int:
    """V_c volume band 1-5 (SRS 5.3)."""
    if rows < 1_000:
        return 1
    if rows < 10_000:
        return 2
    if rows < 100_000:
        return 3
    if rows < 1_000_000:
        return 4
    return 5


@dataclass
class ExposureInputs:
    internet_facing: bool = False
    external_users: bool = False          # consumers / public
    plain_high_or_critical: bool = False  # Critical/High data stored plain
    broad_read_grants: bool = False       # read grants beyond the service account
    processors_outside_india: bool = False


def exposure_multiplier(e: ExposureInputs) -> float:
    """E_app exposure multiplier, product of applicable factors (SRS 5.3)."""
    m = 1.0
    if e.internet_facing:
        m *= 1.5
    if e.external_users:
        m *= 1.3
    if e.plain_high_or_critical:
        m *= 1.5
    if e.broad_read_grants:
        m *= 1.3
    if e.processors_outside_india:
        m *= 1.2
    return m


@dataclass
class CategoryExposure:
    """One inventory line for risk: a category, its tier and its row volume."""

    tier: Tier
    rows: int


def inherent_risk(categories: list[CategoryExposure], exposure: ExposureInputs) -> float:
    e_app = exposure_multiplier(exposure)
    total = 0.0
    for c in categories:
        total += TIER_WEIGHT[c.tier] * volume_band(c.rows) * e_app
    return total


_ANSWER_WEIGHT = {"yes": 1.0, "partial": 0.5, "no": 0.0, "na": None}


def control_effectiveness(answers: dict[str, str], max_eta: float = 0.8) -> float:
    """eta_controls in [0, max_eta] from sections D, E, H, J (SRS 5.3).

    'Yes with evidence' counts full, 'Partial' half, 'No' zero. 'Not applicable'
    answers are excluded from the denominator.
    """
    keys = effectiveness_question_keys()
    considered = 0
    score = 0.0
    for k in keys:
        ans = (answers.get(k) or "").strip().lower()
        weight = _ANSWER_WEIGHT.get(ans)
        if ans == "na" or ans == "":
            continue
        considered += 1
        score += weight or 0.0
    if considered == 0:
        return 0.0
    return max_eta * (score / considered)


def residual_risk(inherent: float, eta: float) -> float:
    return inherent * (1.0 - eta)


def band(score: float, bands=DEFAULT_BANDS) -> RiskBand:
    for name, upper in bands:
        if score < upper:
            return name
    return RiskBand.VERY_HIGH


@dataclass
class RiskResult:
    inherent: float
    residual: float
    eta: float
    exposure_multiplier: float
    inherent_band: RiskBand
    residual_band: RiskBand
    gaps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "inherent": round(self.inherent, 2),
            "residual": round(self.residual, 2),
            "eta_controls": round(self.eta, 3),
            "exposure_multiplier": round(self.exposure_multiplier, 3),
            "inherent_band": self.inherent_band.value,
            "residual_band": self.residual_band.value,
            "gaps": list(self.gaps),
        }


def compute_risk(
    categories: list[CategoryExposure],
    exposure: ExposureInputs,
    answers: dict[str, str] | None = None,
    bands=DEFAULT_BANDS,
) -> RiskResult:
    answers = answers or {}
    e_app = exposure_multiplier(exposure)
    inh = inherent_risk(categories, exposure)
    eta = control_effectiveness(answers)
    res = residual_risk(inh, eta)
    # Any effectiveness question answered No or Partial is a compliance gap.
    gaps = [k for k in effectiveness_question_keys()
            if (answers.get(k) or "").strip().lower() in ("no", "partial")]
    return RiskResult(
        inherent=inh, residual=res, eta=eta, exposure_multiplier=e_app,
        inherent_band=band(inh, bands), residual_band=band(res, bands), gaps=gaps,
    )
