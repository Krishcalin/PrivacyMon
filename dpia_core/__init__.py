"""dpia_core — PrivacyMon's reusable DPIA detection and risk library.

Pure-Python, dependency-free core shared by the API and the scan workers
(SRS section 12.2). Discovers Indian personal data, scores confidence and
sensitivity, maps findings to the DPDP Act 2023, and computes DPIA risk.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .controls import CONTROL_LIBRARY, QUESTIONNAIRE, Control, Framework
from .detectors import DEFAULT_PACK_VERSION, default_detectors, detectors_by_id
from .engine import (
    apply_cooccurrence,
    evaluate_column,
    evaluate_text,
    summarise,
    visible_findings,
)
from .models import (
    Category,
    CATEGORY_LABEL,
    ConfidenceLabel,
    Finding,
    Locator,
    ProtectionState,
    ReviewState,
    ScanProfile,
    Tier,
    confidence_label,
)
from .risk import (
    CategoryExposure,
    ExposureInputs,
    RiskBand,
    RiskResult,
    compute_risk,
)

__all__ = [
    "__version__",
    # detectors
    "default_detectors",
    "detectors_by_id",
    "DEFAULT_PACK_VERSION",
    # engine
    "evaluate_column",
    "evaluate_text",
    "apply_cooccurrence",
    "visible_findings",
    "summarise",
    # models
    "Category",
    "CATEGORY_LABEL",
    "Tier",
    "Finding",
    "Locator",
    "ProtectionState",
    "ReviewState",
    "ScanProfile",
    "ConfidenceLabel",
    "confidence_label",
    # controls
    "CONTROL_LIBRARY",
    "QUESTIONNAIRE",
    "Control",
    "Framework",
    # risk
    "compute_risk",
    "CategoryExposure",
    "ExposureInputs",
    "RiskResult",
    "RiskBand",
]
