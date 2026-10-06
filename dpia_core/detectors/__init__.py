"""Detector subpackage for PrivacyMon's dpia_core."""
from __future__ import annotations

from .base import DetectorSpec, compute_confidence
from .registry import DEFAULT_PACK_VERSION, default_detectors, detectors_by_id

__all__ = [
    "DetectorSpec",
    "compute_confidence",
    "DEFAULT_PACK_VERSION",
    "default_detectors",
    "detectors_by_id",
]
