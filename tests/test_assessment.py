"""DPIA assessment workflow + report — structural (the full flow is validated live)."""
from __future__ import annotations

from types import SimpleNamespace

from api.app import report
from api.app.assessment import _TRANSITIONS
from platform_db.enums import DpiaState


def test_transition_map_covers_every_state_and_the_right_moves():
    assert set(_TRANSITIONS) == set(DpiaState)
    assert _TRANSITIONS[DpiaState.DRAFT] == {DpiaState.SUBMITTED}
    assert _TRANSITIONS[DpiaState.UNDER_REVIEW] == {
        DpiaState.CHANGES_REQUESTED, DpiaState.APPROVED}
    assert _TRANSITIONS[DpiaState.APPROVED] == {DpiaState.PUBLISHED}
    assert _TRANSITIONS[DpiaState.PUBLISHED] == set()


def _fake_data():
    d = SimpleNamespace(
        risk_band=SimpleNamespace(value="high"), inherent_score=120, residual_score=72,
        state=SimpleNamespace(value="published"), approved_at="2026-10-08",
        published_at="2026-10-08")
    app = SimpleNamespace(
        name="HR Portal", environment=SimpleNamespace(value="prod"),
        hosting=SimpleNamespace(value="cloud"), internet_facing=True,
        user_base=SimpleNamespace(value="customers"))
    return {
        "dpia": d, "app": app,
        "sections": [{"key": "A", "title": "Processing overview", "questions": [
            {"key": "A1", "text": "Purpose?", "answer": "Yes", "justification": "KYC"}]}],
        "inventory": {"pan": {"tier": "high", "locations_count": 2}},
        "risks": [{"title": "[gap] E1: encryption", "likelihood": 3, "impact": 5,
                   "treatment": "mitigate", "status": "open"}],
    }


def test_report_html_includes_the_key_sections():
    doc = report.render_html(_fake_data())
    assert "Data Protection Impact Assessment" in doc
    assert "HR Portal" in doc
    assert "pan" in doc           # inventory
    assert "A1" in doc            # questionnaire
    assert "[gap] E1: encryption" in doc  # risk register
    assert "%PDF" not in doc      # it is HTML, not PDF
