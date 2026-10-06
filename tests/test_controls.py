"""DPDP control library and questionnaire structure (SRS 5.1, 5.2)."""
from __future__ import annotations

from dpia_core.controls import (
    CONTROL_LIBRARY,
    QUESTIONNAIRE,
    effectiveness_question_keys,
    question_keys,
)


def test_control_library_covers_core_sections():
    refs = " ".join(c.ref for c in CONTROL_LIBRARY)
    for section in ("S.4", "S.5", "S.7", "S.8", "S.9", "S.10", "S.16", "S.33"):
        assert section in refs


def test_every_control_has_check_and_evidence():
    for c in CONTROL_LIBRARY:
        assert c.obligation and c.platform_check and c.evidence_source


def test_questionnaire_has_all_sections():
    keys = [s.key for s in QUESTIONNAIRE]
    assert keys == list("ABCDEFGHIJK")


def test_question_keys_unique():
    keys = question_keys()
    assert len(keys) == len(set(keys))


def test_effectiveness_keys_from_DEHJ():
    eff = effectiveness_question_keys()
    assert all(k[0] in {"D", "E", "H", "J"} for k in eff)
    assert len(eff) == 15  # D:3 + E:5 + H:4 + J:3
