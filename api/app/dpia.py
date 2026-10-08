"""DPIA processing-record endpoints (the 30-field "DPIA Fields" sheet).

Each record is one processing activity for an application, carrying the 30 DPDP
parameters. Most are free text; two are booleans. Create/update accept any subset.
Pre-auth these read/write as the owner; they move to the scoped role + RLS context
with auth.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from platform_db.models.registry import Application
from platform_db.models.assessment import DpiaRecord

from . import db
from .settings import settings

router = APIRouter(prefix=settings.api_prefix)

# The 30 DPDP fields (order = the DPIA Fields sheet). Two are booleans; the rest text.
TEXT_FIELDS = [
    "inventory_id", "business_function", "data_principal_type", "data_category",
    "data_elements", "purpose_of_processing", "legal_basis", "source_system",
    "target_systems", "retention_period", "deletion_trigger", "data_owner",
    "processor_involved", "encryption_status", "hosting_location", "log_retention",
    "technical_safeguards", "organizational_safeguards", "security_certifications",
    "breach_sla", "audit_rights", "consent_withdrawal_mode", "dpo_approval",
    "data_principal_rights", "children_data_protection", "grievance_redressal",
    "cross_border_transfers", "tracking_cookies",
]
BOOL_FIELDS = ["sensitive_high_risk", "dpa_signed"]
ALL_FIELDS = TEXT_FIELDS + BOOL_FIELDS


class DpiaRecordBody(BaseModel):
    inventory_id: str | None = None
    business_function: str | None = None
    data_principal_type: str | None = None
    data_category: str | None = None
    data_elements: str | None = None
    sensitive_high_risk: bool = False
    purpose_of_processing: str | None = None
    legal_basis: str | None = None
    source_system: str | None = None
    target_systems: str | None = None
    retention_period: str | None = None
    deletion_trigger: str | None = None
    data_owner: str | None = None
    processor_involved: str | None = None
    encryption_status: str | None = None
    hosting_location: str | None = None
    log_retention: str | None = None
    technical_safeguards: str | None = None
    organizational_safeguards: str | None = None
    dpa_signed: bool = False
    security_certifications: str | None = None
    breach_sla: str | None = None
    audit_rights: str | None = None
    consent_withdrawal_mode: str | None = None
    dpo_approval: str | None = None
    data_principal_rights: str | None = None
    children_data_protection: str | None = None
    grievance_redressal: str | None = None
    cross_border_transfers: str | None = None
    tracking_cookies: str | None = None


def _record_dict(r: DpiaRecord) -> dict:
    return {
        "id": str(r.id),
        "application_id": str(r.application_id),
        **{f: getattr(r, f) for f in ALL_FIELDS},
    }


@router.get("/applications/{application_id}/dpia-records")
def list_records(application_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        rows = s.query(DpiaRecord).filter(
            DpiaRecord.application_id == application_id).order_by(
            DpiaRecord.created_at).all()
        return {"count": len(rows), "records": [_record_dict(r) for r in rows]}


@router.post("/applications/{application_id}/dpia-records", status_code=201)
def create_record(application_id: uuid.UUID, body: DpiaRecordBody) -> dict:
    with db.get_sessionmaker()() as s:
        if s.get(Application, application_id) is None:
            raise HTTPException(status_code=404, detail="application not found")
        rec = DpiaRecord(application_id=application_id, **body.model_dump())
        s.add(rec)
        s.commit()
        return _record_dict(rec)


@router.get("/dpia-records/{record_id}")
def get_record(record_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        rec = s.get(DpiaRecord, record_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="DPIA record not found")
        return _record_dict(rec)


@router.put("/dpia-records/{record_id}")
def update_record(record_id: uuid.UUID, body: DpiaRecordBody) -> dict:
    with db.get_sessionmaker()() as s:
        rec = s.get(DpiaRecord, record_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="DPIA record not found")
        for field, value in body.model_dump().items():
            setattr(rec, field, value)
        s.commit()
        return _record_dict(rec)


@router.delete("/dpia-records/{record_id}", status_code=204)
def delete_record(record_id: uuid.UUID) -> None:
    with db.get_sessionmaker()() as s:
        rec = s.get(DpiaRecord, record_id)
        if rec is not None:
            s.delete(rec)
            s.commit()
