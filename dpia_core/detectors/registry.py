"""Default detector pack assembly (SRS section 7.3).

A pack is a versioned collection of detectors. Custom detectors created in the
UI (FR-4.7) are compiled into the same chain at scan start; here we expose the
built-in pack.
"""
from __future__ import annotations

from .base import DetectorSpec
from .dictionary import build_dictionary_detectors
from .structured import build_structured_detectors

DEFAULT_PACK_VERSION = "builtin-1.0.0"


def default_detectors() -> list[DetectorSpec]:
    """The built-in detector pack: structured identifiers + dictionary/NER."""
    return build_structured_detectors() + build_dictionary_detectors()


def detectors_by_id() -> dict[str, DetectorSpec]:
    return {d.id: d for d in default_detectors()}
