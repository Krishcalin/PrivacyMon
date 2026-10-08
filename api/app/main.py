"""PrivacyMon API (SRS section 9) — Phase 1 surface.

This increment exposes the health, control-library and detector-test endpoints,
all backed by ``dpia_core``. The database-backed resources (applications, data
sources, scans, findings, DPIAs) and OIDC auth land in the next increment once
PostgreSQL, Redis and Celery are provisioned.
"""
from __future__ import annotations

from fastapi import FastAPI, Query, Response
from pydantic import BaseModel, Field

import dpia_core
from dpia_core.controls import CONTROL_LIBRARY, QUESTIONNAIRE
from dpia_core.detectors import DEFAULT_PACK_VERSION, default_detectors
from dpia_core.engine import evaluate_column, visible_findings

from . import db
from .settings import settings

app = FastAPI(
    title="PrivacyMon DPIA Platform API",
    version=dpia_core.__version__,
    docs_url=f"{settings.api_prefix}/docs" if settings.enable_docs else None,
    openapi_url=f"{settings.api_prefix}/openapi.json" if settings.enable_docs else None,
)

P = settings.api_prefix


@app.get(f"{P}/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get(f"{P}/readyz")
def readyz(response: Response) -> dict:
    """Readiness: PostgreSQL reachable (SRS 9 /readyz). Returns 503 when the platform
    database is unavailable so an orchestrator holds traffic until it is."""
    ok, detail = db.db_ok()
    if not ok:
        response.status_code = 503
    return {"status": "ready" if ok else "degraded",
            "checks": {"dpia_core": "ok", "database": detail}}


@app.get(f"{P}/version")
def version() -> dict:
    return {
        "app": settings.app_name,
        "api_version": dpia_core.__version__,
        "detector_pack": DEFAULT_PACK_VERSION,
        "environment": settings.environment,
    }


@app.get(f"{P}/controls")
def controls(framework: str = Query("dpdp")) -> dict:
    """Control library (SRS 9: GET /controls?framework=dpdp)."""
    items = [
        {
            "ref": c.ref,
            "obligation": c.obligation,
            "platform_check": c.platform_check,
            "evidence_source": c.evidence_source,
            "question_keys": list(c.question_keys),
            "iso27701": list(c.iso27701),
            "iso27001": list(c.iso27001),
            "certin": list(c.certin),
        }
        for c in CONTROL_LIBRARY
    ]
    return {"framework": framework, "count": len(items), "controls": items}


@app.get(f"{P}/questionnaire")
def questionnaire() -> dict:
    return {
        "sections": [
            {
                "key": s.key,
                "title": s.title,
                "answered_by": s.answered_by,
                "questions": [
                    {"key": q.key, "text": q.text, "guidance": q.guidance}
                    for q in s.questions
                ],
            }
            for s in QUESTIONNAIRE
        ]
    }


@app.get(f"{P}/detectors")
def detectors() -> dict:
    items = [
        {
            "id": d.id,
            "category": d.category.value,
            "tier": d.tier.value,
            "kind": d.kind.value,
            "base_score": d.base_score,
            "requires_context": d.requires_context,
            "context_positive": d.context_positive,
            "description": d.description,
        }
        for d in default_detectors()
    ]
    return {"pack_version": DEFAULT_PACK_VERSION, "count": len(items), "detectors": items}


class DetectorTestRequest(BaseModel):
    """Run detectors against submitted sample strings (SRS 9: detectors/test)."""

    samples: list[str] = Field(..., min_length=1, max_length=1000)
    column_name: str | None = None
    data_type: str | None = None


@app.post(f"{P}/detectors/test")
def detectors_test(req: DetectorTestRequest) -> dict:
    findings = evaluate_column(
        default_detectors(),
        req.column_name,
        req.samples,
        data_type=req.data_type,
        pack_version=DEFAULT_PACK_VERSION,
    )
    shown = visible_findings(findings, settings.review_threshold)
    return {
        "input_count": len(req.samples),
        "finding_count": len(shown),
        "findings": [f.as_dict() for f in shown],
    }


@app.get(f"{P}/applications")
def applications() -> dict:
    """List registered applications from the platform DB (SRS 9: GET /applications).

    A first database-backed resource proving the app↔db wiring; the full registry CRUD,
    scoping and OIDC auth land with the auth slice.
    """
    from platform_db.models.registry import Application

    sessionmaker = db.get_sessionmaker()
    with sessionmaker() as s:
        rows = s.query(Application).order_by(Application.created_at).all()
        return {
            "count": len(rows),
            "applications": [
                {
                    "id": str(a.id),
                    "name": a.name,
                    "environment": a.environment.value if a.environment else None,
                    "lifecycle": a.lifecycle.value if a.lifecycle else None,
                    "internet_facing": a.internet_facing,
                }
                for a in rows
            ],
        }
