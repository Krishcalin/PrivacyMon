"""DPIA assessment workflow (SRS 3.6 / 5 / 9): create a DPIA, answer the A–K
questionnaire (pre-filled from the scan where possible), compute inherent/residual
risk and the risk register, move it through the workflow, and comment.

The questionnaire, control library and risk engine live in ``dpia_core``; this wires
them to the ``dpia_assessments`` / ``questionnaire_responses`` / ``risks`` /
``dpia_transitions`` / ``dpia_comments`` tables and the React workspace.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text

from dpia_core.controls import QUESTIONNAIRE, effectiveness_question_keys
from dpia_core.models import Tier
from dpia_core.risk import CategoryExposure, ExposureInputs, compute_risk
from platform_db.enums import Answer, DpiaState, RiskBand, RiskStatus, Treatment
from platform_db.models.assessment import (
    DpiaAssessment, DpiaComment, DpiaTransition, QuestionnaireResponse, Risk,
)
from platform_db.models.registry import Application
from platform_db.models.scanning import Inventory

from . import db
from .settings import settings

router = APIRouter(prefix=settings.api_prefix)

TEMPLATE_VERSION = "dpdp-A-K-1.0.0"

# Allowed workflow moves (SRS FR-6.3): Draft → Submitted → Under review →
# Changes requested → Approved → Published.
_TRANSITIONS: dict[DpiaState, set[DpiaState]] = {
    DpiaState.DRAFT: {DpiaState.SUBMITTED},
    DpiaState.SUBMITTED: {DpiaState.UNDER_REVIEW},
    DpiaState.UNDER_REVIEW: {DpiaState.CHANGES_REQUESTED, DpiaState.APPROVED},
    DpiaState.CHANGES_REQUESTED: {DpiaState.SUBMITTED},
    DpiaState.APPROVED: {DpiaState.PUBLISHED},
    DpiaState.PUBLISHED: set(),
}
_QUESTION = {q.key: q for s in QUESTIONNAIRE for q in s.questions}


# ── request models ───────────────────────────────────────────────────────────
class AnswerBody(BaseModel):
    answer: Answer
    justification: str | None = None


class TransitionBody(BaseModel):
    to: DpiaState
    note: str | None = None


class CommentBody(BaseModel):
    question_key: str | None = None
    body: str = Field(..., min_length=1)


class RiskBody(BaseModel):
    title: str = Field(..., min_length=1)
    likelihood: int = Field(3, ge=1, le=5)
    impact: int = Field(3, ge=1, le=5)
    treatment: Treatment | None = None
    treatment_plan: str | None = None
    status: RiskStatus = RiskStatus.OPEN


# ── helpers ──────────────────────────────────────────────────────────────────
def _snapshot_inventory(s, application_id: uuid.UUID) -> dict:
    rows = s.query(Inventory).filter(Inventory.application_id == application_id).all()
    return {
        r.category.value: {
            "tier": r.tier.value, "rows_estimate": r.rows_estimate,
            "locations_count": r.locations_count,
            "protection": r.protection_state_summary or {},
        } for r in rows
    }


def _suggestions(app: Application, inventory: dict) -> dict[str, dict]:
    """Pre-fill hints from the scan + registry (SRS FR-6.2). Suggestions only — the
    owner confirms or edits them; nothing is persisted until they save."""
    out: dict[str, dict] = {}
    if app.user_base:
        out["A2"] = {"answer": "yes", "justification": f"Data principals: {app.user_base.value}."}
    if app.approx_records:
        out["A3"] = {"answer": "na", "justification": f"Approx. {app.approx_records:,} records."}
    out["G1"] = {"answer": "na", "justification": f"Hosting: {app.hosting.value}."}
    if "children_data" in inventory:
        out["I1"] = {"answer": "yes",
                     "justification": "Children's data (DOB implying age < 18) detected by the scan."}
    plain_hi = any(inv["protection"].get("plain", 0) > 0 and inv["tier"] in ("high", "critical")
                   for inv in inventory.values())
    if plain_hi:
        out["E1"] = {"answer": "no",
                     "justification": "Scan found high/critical personal data stored in plain text."}
    crit = sorted(c for c, inv in inventory.items() if inv["tier"] == "critical")
    if crit:
        out["A1"] = {"answer": "na",
                     "justification": f"Critical categories in scope: {', '.join(crit)}."}
    return out


def _dpia_dict(d: DpiaAssessment) -> dict:
    return {
        "id": str(d.id), "application_id": str(d.application_id),
        "state": d.state.value, "template_version": d.template_version,
        "needs_review": d.needs_review,
        "inherent_score": float(d.inherent_score) if d.inherent_score is not None else None,
        "residual_score": float(d.residual_score) if d.residual_score is not None else None,
        "risk_band": d.risk_band.value if d.risk_band else None,
    }


def _risk_dict(r: Risk) -> dict:
    return {
        "id": str(r.id), "title": r.title, "likelihood": r.likelihood, "impact": r.impact,
        "inherent_score": float(r.inherent_score) if r.inherent_score is not None else None,
        "treatment": r.treatment.value if r.treatment else None,
        "treatment_plan": r.treatment_plan,
        "status": r.status.value,
    }


def _recompute(s, dpia: DpiaAssessment) -> None:
    """Recompute inherent/residual risk from the inventory snapshot + answers, and
    rebuild the AUTO gap-derived risk register entries (manual ones are kept)."""
    app = s.get(Application, dpia.application_id)
    inventory = dpia.inventory_snapshot or {}
    answers = {
        r.question_key: r.answer.value for r in s.query(QuestionnaireResponse).filter(
            QuestionnaireResponse.dpia_id == dpia.id).all()
    }
    categories = [CategoryExposure(tier=Tier(inv["tier"]), rows=inv.get("rows_estimate", 0))
                  for inv in inventory.values()]
    plain_hi = any(inv["protection"].get("plain", 0) > 0 and inv["tier"] in ("high", "critical")
                   for inv in inventory.values())
    ub = getattr(app.user_base, "value", None)
    exposure = ExposureInputs(
        internet_facing=bool(app.internet_facing),
        external_users=ub in ("customers", "public"),
        plain_high_or_critical=plain_hi)
    result = compute_risk(categories, exposure, answers)

    dpia.inherent_score = round(result.inherent, 2)
    dpia.residual_score = round(result.residual, 2)
    dpia.risk_band = RiskBand(result.residual_band.value)

    # Rebuild auto gap risks (title marked "[gap]"); leave manual risks untouched.
    s.execute(delete(Risk).where(Risk.dpia_id == dpia.id,
                                 Risk.title.like("[gap]%")))
    impact = 5 if any(inv["tier"] == "critical" for inv in inventory.values()) else (
        4 if any(inv["tier"] == "high" for inv in inventory.values()) else 3)
    for key in result.gaps:
        q = _QUESTION.get(key)
        s.add(Risk(
            dpia_id=dpia.id, application_id=dpia.application_id,
            title=f"[gap] {key}: {q.text if q else key}",
            likelihood=3, impact=impact,
            treatment=Treatment.MITIGATE, status=RiskStatus.OPEN))


def _get_dpia(s, dpia_id: uuid.UUID) -> DpiaAssessment:
    d = s.get(DpiaAssessment, dpia_id)
    if d is None:
        raise HTTPException(status_code=404, detail="DPIA not found")
    return d


# ── DPIA lifecycle ───────────────────────────────────────────────────────────
@router.post("/applications/{application_id}/dpias", status_code=201)
def create_dpia(application_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        if s.get(Application, application_id) is None:
            raise HTTPException(status_code=404, detail="application not found")
        dpia = DpiaAssessment(
            application_id=application_id, template_version=TEMPLATE_VERSION,
            state=DpiaState.DRAFT,
            inventory_snapshot=_snapshot_inventory(s, application_id))
        s.add(dpia)
        s.flush()
        s.add(DpiaTransition(dpia_id=dpia.id, application_id=application_id,
                             from_state=None, to_state=DpiaState.DRAFT, note="created"))
        _recompute(s, dpia)
        s.commit()
        return _dpia_dict(dpia)


@router.get("/applications/{application_id}/dpias")
def list_dpias(application_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        rows = s.query(DpiaAssessment).filter(
            DpiaAssessment.application_id == application_id).order_by(
            DpiaAssessment.created_at.desc()).all()
        return {"count": len(rows), "dpias": [_dpia_dict(d) for d in rows]}


@router.get("/dpias/{dpia_id}")
def get_dpia(dpia_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        d = _get_dpia(s, dpia_id)
        app = s.get(Application, d.application_id)
        return {**_dpia_dict(d), "application_name": app.name if app else None,
                "inventory_snapshot": d.inventory_snapshot or {}}


@router.get("/dpias/{dpia_id}/questionnaire")
def get_questionnaire(dpia_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        d = _get_dpia(s, dpia_id)
        app = s.get(Application, d.application_id)
        responses = {
            r.question_key: r for r in s.query(QuestionnaireResponse).filter(
                QuestionnaireResponse.dpia_id == dpia_id).all()
        }
        suggestions = _suggestions(app, d.inventory_snapshot or {})
        eff = set(effectiveness_question_keys())
        sections = []
        for sec in QUESTIONNAIRE:
            sections.append({
                "key": sec.key, "title": sec.title, "answered_by": sec.answered_by,
                "questions": [{
                    "key": q.key, "text": q.text, "guidance": q.guidance,
                    "affects_risk": q.key in eff,
                    "answer": responses[q.key].answer.value if q.key in responses else None,
                    "justification": responses[q.key].justification if q.key in responses else None,
                    "suggestion": suggestions.get(q.key),
                } for q in sec.questions],
            })
        answered = len(responses)
        total = sum(len(sec.questions) for sec in QUESTIONNAIRE)
        return {"dpia_id": str(dpia_id), "state": d.state.value,
                "answered": answered, "total": total, "sections": sections}


@router.put("/dpias/{dpia_id}/responses/{question_key}")
def save_response(dpia_id: uuid.UUID, question_key: str, body: AnswerBody) -> dict:
    if question_key not in _QUESTION:
        raise HTTPException(status_code=400, detail="unknown question key")
    with db.get_sessionmaker()() as s:
        d = _get_dpia(s, dpia_id)
        existing = s.execute(select(QuestionnaireResponse).where(
            QuestionnaireResponse.dpia_id == dpia_id,
            QuestionnaireResponse.question_key == question_key)).scalars().first()
        if existing:
            existing.answer = body.answer
            existing.justification = body.justification
        else:
            s.add(QuestionnaireResponse(
                dpia_id=dpia_id, application_id=d.application_id,
                question_key=question_key, answer=body.answer,
                justification=body.justification))
        _recompute(s, d)
        s.commit()
        return {"ok": True, "risk_band": d.risk_band.value if d.risk_band else None}


@router.post("/dpias/{dpia_id}/recompute")
def recompute_dpia(dpia_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        d = _get_dpia(s, dpia_id)
        _recompute(s, d)
        s.commit()
        return _dpia_dict(d)


@router.post("/dpias/{dpia_id}/transition")
def transition_dpia(dpia_id: uuid.UUID, body: TransitionBody) -> dict:
    with db.get_sessionmaker()() as s:
        d = _get_dpia(s, dpia_id)
        if body.to not in _TRANSITIONS.get(d.state, set()):
            raise HTTPException(
                status_code=409,
                detail=f"cannot move a {d.state.value} DPIA to {body.to.value}")
        from_state = d.state
        d.state = body.to
        if body.to == DpiaState.APPROVED:
            d.approved_at = text("now()")
        if body.to == DpiaState.PUBLISHED:
            d.published_at = text("now()")
        if body.to == DpiaState.SUBMITTED:
            d.submitted_at = text("now()")
        s.add(DpiaTransition(dpia_id=dpia_id, application_id=d.application_id,
                             from_state=from_state, to_state=body.to, note=body.note))
        s.commit()
        return _dpia_dict(d)


# ── risk register ────────────────────────────────────────────────────────────
@router.get("/dpias/{dpia_id}/risks")
def list_risks(dpia_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        rows = s.query(Risk).filter(Risk.dpia_id == dpia_id).order_by(
            Risk.created_at).all()
        return {"count": len(rows), "risks": [_risk_dict(r) for r in rows]}


@router.post("/dpias/{dpia_id}/risks", status_code=201)
def add_risk(dpia_id: uuid.UUID, body: RiskBody) -> dict:
    with db.get_sessionmaker()() as s:
        d = _get_dpia(s, dpia_id)
        r = Risk(dpia_id=dpia_id, application_id=d.application_id, title=body.title,
                 likelihood=body.likelihood, impact=body.impact,
                 inherent_score=body.likelihood * body.impact,
                 treatment=body.treatment, treatment_plan=body.treatment_plan,
                 status=body.status)
        s.add(r)
        s.commit()
        return _risk_dict(r)


# ── comments ─────────────────────────────────────────────────────────────────
@router.get("/dpias/{dpia_id}/comments")
def list_comments(dpia_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        rows = s.query(DpiaComment).filter(DpiaComment.dpia_id == dpia_id).order_by(
            DpiaComment.created_at).all()
        return {"count": len(rows), "comments": [{
            "id": str(c.id), "question_key": c.question_key, "body": c.body,
            "resolved": c.resolved} for c in rows]}


@router.post("/dpias/{dpia_id}/comments", status_code=201)
def add_comment(dpia_id: uuid.UUID, body: CommentBody) -> dict:
    with db.get_sessionmaker()() as s:
        d = _get_dpia(s, dpia_id)
        c = DpiaComment(dpia_id=dpia_id, application_id=d.application_id,
                        question_key=body.question_key, body=body.body)
        s.add(c)
        s.commit()
        return {"id": str(c.id)}
