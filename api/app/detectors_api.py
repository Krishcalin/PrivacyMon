"""Custom detector management API (SRS FR-4.7, platform admin).

An admin defines extra detectors through the console: a PII category, a tier, an optional
regex, an optional named validator, and column-name context keywords. They are stored in
a single active CUSTOM detector pack and merged into every scan's detector chain. Each
definition is validated by compiling it (the same compiler the worker uses) before it is
saved, so a bad regex or unknown validator is rejected with a clear message rather than
silently dropped at scan time.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dpia_core.detectors.compile import (
    DetectorCompileError, spec_from_row, validator_names,
)
from dpia_core.models import Category, Tier
from platform_db.enums import DetectorPackSource
from platform_db.models.scanning import Detector, DetectorPack

from . import audit, db
from .auth import Principal, require_global
from .settings import settings

router = APIRouter(prefix=settings.api_prefix)

_CUSTOM_PACK_NAME = "custom"
_CUSTOM_PACK_VERSION = "custom-1.0.0"


def _custom_pack(s) -> DetectorPack:
    """Get or create the single active custom pack."""
    pack = s.query(DetectorPack).filter(
        DetectorPack.name == _CUSTOM_PACK_NAME,
        DetectorPack.source == DetectorPackSource.CUSTOM).first()
    if pack is None:
        pack = DetectorPack(name=_CUSTOM_PACK_NAME, version=_CUSTOM_PACK_VERSION,
                            source=DetectorPackSource.CUSTOM, active=True, manifest={})
        s.add(pack)
        s.flush()
    return pack


class CreateDetector(BaseModel):
    category: Category
    tier: Tier
    pattern: str | None = None
    validator: str | None = None
    context_positive: list[str] = Field(default_factory=list)
    context_negative: list[str] = Field(default_factory=list)
    description: str = ""


@router.get("/admin/detectors")
def list_custom_detectors(_admin: Principal = Depends(require_global("admin"))) -> dict:
    with db.get_sessionmaker()() as s:
        pack = s.query(DetectorPack).filter(
            DetectorPack.name == _CUSTOM_PACK_NAME,
            DetectorPack.source == DetectorPackSource.CUSTOM).first()
        rows = [] if pack is None else s.query(Detector).filter(
            Detector.pack_id == pack.id).order_by(Detector.created_at).all()
        return {
            "validators": validator_names(),
            "pack_active": bool(pack.active) if pack else True,
            "count": len(rows),
            "detectors": [{
                "id": str(d.id), "category": d.category.value, "tier": d.tier.value,
                "pattern": d.pattern, "validator": d.validator,
                "context_positive": list(d.context_positive or []),
                "context_negative": list(d.context_negative or []),
            } for d in rows],
        }


@router.post("/admin/detectors", status_code=201)
def create_custom_detector(body: CreateDetector,
                           admin: Principal = Depends(require_global("admin"))) -> dict:
    from dpia_core.detectors.base import BASE_SCORE
    # Validate by compiling BEFORE persisting — reject a bad regex / unknown validator.
    try:
        spec = spec_from_row({
            "id": "preview", "category": body.category, "tier": body.tier,
            "pattern": body.pattern, "validator": body.validator,
            "context_positive": body.context_positive,
            "context_negative": body.context_negative,
        })
    except DetectorCompileError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with db.get_sessionmaker()() as s:
        pack = _custom_pack(s)
        det = Detector(
            pack_id=pack.id, category=body.category, tier=body.tier,
            pattern=body.pattern, validator=body.validator,
            context_positive=body.context_positive,
            context_negative=body.context_negative,
            base_score=BASE_SCORE[spec.kind])
        s.add(det)
        s.flush()
        audit.record(s, actor_id=admin.user_id, action="detector.create",
                     object_type="detector", object_id=str(det.id),
                     after={"category": body.category.value, "tier": body.tier.value,
                            "pattern": body.pattern, "validator": body.validator})
        s.commit()
        return {"id": str(det.id)}


@router.delete("/admin/detectors/{detector_id}", status_code=204)
def delete_custom_detector(detector_id: uuid.UUID,
                           admin: Principal = Depends(require_global("admin"))) -> None:
    with db.get_sessionmaker()() as s:
        det = s.get(Detector, detector_id)
        if det is None:
            raise HTTPException(status_code=404, detail="detector not found")
        audit.record(s, actor_id=admin.user_id, action="detector.delete",
                     object_type="detector", object_id=str(det.id),
                     before={"category": det.category.value})
        s.delete(det)
        s.commit()
