"""Console-backing endpoints (SRS 9/10): application registry, findings explorer,
data inventory, and the portfolio dashboard aggregate.

These read and write the platform DB for the React SPA. Pre-auth, the API connects
as the owner (RLS bypassed); once OIDC lands it connects as ``privacymon_app`` and
scopes every query to the caller's applications via the RLS session context.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from platform_db.enums import (
    DataSourceKind, Environment, Hosting, Lifecycle, ScanProfile, UserBase,
)
from platform_db.models.registry import Application, DataSource
from platform_db.models.scanning import Finding, Inventory, ScanJob

from . import db
from .settings import settings

router = APIRouter(prefix=settings.api_prefix)


# ── request models ───────────────────────────────────────────────────────────
class RegisterApplication(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    environment: Environment
    hosting: Hosting
    internet_facing: bool = False
    user_base: UserBase | None = None
    approx_records: int | None = None
    lifecycle: Lifecycle = Lifecycle.DRAFT
    tags: list[str] = Field(default_factory=list)


class AddDataSource(BaseModel):
    kind: DataSourceKind
    display_name: str = Field(..., min_length=1, max_length=200)
    connection: dict = Field(default_factory=dict)
    credential_ref: str | None = None
    scan_profile_default: ScanProfile = ScanProfile.STANDARD
    schedule_cron: str | None = None


# ── serialisers ──────────────────────────────────────────────────────────────
def _app_dict(a: Application) -> dict:
    return {
        "id": str(a.id), "name": a.name, "description": a.description,
        "environment": a.environment.value, "hosting": a.hosting.value,
        "internet_facing": a.internet_facing,
        "user_base": a.user_base.value if a.user_base else None,
        "approx_records": a.approx_records, "lifecycle": a.lifecycle.value,
        "tags": list(a.tags or []),
    }


def _source_dict(s: DataSource) -> dict:
    return {
        "id": str(s.id), "application_id": str(s.application_id),
        "kind": s.kind.value, "display_name": s.display_name,
        "connection": s.connection or {},
        "credential_configured": bool(s.credential_ref),
        "scan_profile_default": s.scan_profile_default.value,
        "schedule_cron": s.schedule_cron,
    }


# ── applications ─────────────────────────────────────────────────────────────
@router.get("/applications")
def list_applications() -> dict:
    with db.get_sessionmaker()() as s:
        rows = s.query(Application).order_by(Application.created_at).all()
        return {"count": len(rows), "applications": [_app_dict(a) for a in rows]}


@router.post("/applications", status_code=201)
def register_application(body: RegisterApplication) -> dict:
    with db.get_sessionmaker()() as s:
        app = Application(
            name=body.name, description=body.description,
            environment=body.environment, hosting=body.hosting,
            internet_facing=body.internet_facing, user_base=body.user_base,
            approx_records=body.approx_records, lifecycle=body.lifecycle,
            tags=body.tags)
        s.add(app)
        s.commit()
        return _app_dict(app)


@router.get("/applications/{application_id}")
def get_application(application_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        app = s.get(Application, application_id)
        if app is None:
            raise HTTPException(status_code=404, detail="application not found")
        sources = s.query(DataSource).filter(
            DataSource.application_id == application_id).count()
        by_tier = dict(s.execute(
            select(Finding.tier, func.count()).where(
                Finding.application_id == application_id).group_by(Finding.tier)).all())
        categories = s.query(Inventory).filter(
            Inventory.application_id == application_id).count()
        last_scan = s.execute(
            select(ScanJob).where(ScanJob.application_id == application_id)
            .order_by(ScanJob.created_at.desc()).limit(1)).scalars().first()
        return {
            **_app_dict(app),
            "data_sources": sources,
            "inventory_categories": categories,
            "findings_by_tier": {t.value: n for t, n in by_tier.items()},
            "last_scan": None if last_scan is None else {
                "job_id": str(last_scan.id), "state": last_scan.state.value,
                "findings_count": last_scan.findings_count},
        }


# ── data sources ─────────────────────────────────────────────────────────────
@router.get("/applications/{application_id}/data-sources")
def list_data_sources(application_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        rows = s.query(DataSource).filter(
            DataSource.application_id == application_id).order_by(
            DataSource.created_at).all()
        return {"count": len(rows), "data_sources": [_source_dict(d) for d in rows]}


@router.post("/applications/{application_id}/data-sources", status_code=201)
def add_data_source(application_id: uuid.UUID, body: AddDataSource) -> dict:
    with db.get_sessionmaker()() as s:
        if s.get(Application, application_id) is None:
            raise HTTPException(status_code=404, detail="application not found")
        ds = DataSource(
            application_id=application_id, kind=body.kind,
            display_name=body.display_name, connection=body.connection,
            credential_ref=body.credential_ref,
            scan_profile_default=body.scan_profile_default,
            schedule_cron=body.schedule_cron)
        s.add(ds)
        s.commit()
        return _source_dict(ds)


# ── findings explorer ────────────────────────────────────────────────────────
@router.get("/applications/{application_id}/findings")
def list_findings(
    application_id: uuid.UUID,
    category: str | None = None,
    tier: str | None = None,
    review_state: str | None = None,
    min_confidence: float = 0.0,
    limit: int = Query(200, le=1000),
    offset: int = 0,
) -> dict:
    with db.get_sessionmaker()() as s:
        q = s.query(Finding).filter(Finding.application_id == application_id)
        if category:
            q = q.filter(Finding.category == category)
        if tier:
            q = q.filter(Finding.tier == tier)
        if review_state:
            q = q.filter(Finding.review_state == review_state)
        if min_confidence:
            q = q.filter(Finding.confidence >= min_confidence)
        total = q.count()
        rows = q.order_by(Finding.confidence.desc()).offset(offset).limit(limit).all()
        return {
            "total": total, "limit": limit, "offset": offset,
            "findings": [{
                "id": str(f.id),
                "category": f.category.value, "tier": f.tier.value,
                "confidence": float(f.confidence), "hit_rate": float(f.hit_rate),
                "locator": f.locator, "protection_state": f.protection_state.value,
                "combined_identity": f.combined_identity,
                "review_state": f.review_state.value, "evidence": f.evidence or [],
            } for f in rows],
        }


# ── data inventory ───────────────────────────────────────────────────────────
@router.get("/applications/{application_id}/inventory")
def get_inventory(application_id: uuid.UUID) -> dict:
    with db.get_sessionmaker()() as s:
        rows = s.query(Inventory).filter(
            Inventory.application_id == application_id).order_by(
            Inventory.category).all()
        return {"count": len(rows), "inventory": [{
            "category": i.category.value, "tier": i.tier.value,
            "locations_count": i.locations_count, "rows_estimate": i.rows_estimate,
            "protection_state_summary": i.protection_state_summary or {},
            "purpose": i.purpose, "source_of_data": i.source_of_data,
            "recipients": i.recipients,
        } for i in rows]}


# ── portfolio dashboard ──────────────────────────────────────────────────────
@router.get("/dashboard/portfolio")
def portfolio() -> dict:
    """Aggregate for the dashboard: per-application category coverage + top tier,
    portfolio totals, and a scan-coverage gauge."""
    _TIER_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    with db.get_sessionmaker()() as s:
        apps = s.query(Application).order_by(Application.name).all()
        inv_rows = s.query(Inventory).all()
        by_app: dict[str, list] = {}
        for i in inv_rows:
            by_app.setdefault(str(i.application_id), []).append(i)
        scanned_ids = {str(a) for (a,) in s.execute(
            select(Finding.application_id).distinct()).all()}
        tier_totals = dict(s.execute(
            select(Finding.tier, func.count()).group_by(Finding.tier)).all())
        categories_seen: set[str] = set()

        app_cards = []
        for a in apps:
            inv = by_app.get(str(a.id), [])
            cats = sorted({i.category.value for i in inv})
            categories_seen.update(cats)
            top = max((i.tier.value for i in inv), key=lambda t: _TIER_RANK[t],
                      default=None)
            app_cards.append({
                "id": str(a.id), "name": a.name, "lifecycle": a.lifecycle.value,
                "environment": a.environment.value,
                "internet_facing": a.internet_facing, "tags": list(a.tags or []),
                "categories": cats, "top_tier": top,
                "scanned": str(a.id) in scanned_ids,
            })

        return {
            "totals": {
                "applications": len(apps),
                "scanned": len(scanned_ids),
                "findings": sum(int(n) for n in tier_totals.values()),
                "by_tier": {t.value: int(n) for t, n in tier_totals.items()},
            },
            "coverage": round(len(scanned_ids) / len(apps), 3) if apps else 0.0,
            "categories": sorted(categories_seen),
            "applications": app_cards,
        }
