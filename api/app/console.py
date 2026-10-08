"""Console-backing endpoints (SRS 9/10): application registry, findings explorer,
data inventory, and the portfolio dashboard aggregate.

These read and write the platform DB for the React SPA. Pre-auth, the API connects
as the owner (RLS bypassed); once OIDC lands it connects as ``privacymon_app`` and
scopes every query to the caller's applications via the RLS session context.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from platform_db import crypto
from platform_db.enums import (
    DataSourceKind, Environment, Hosting, Lifecycle, Role, ScanProfile, UserBase,
)
from platform_db.enums import Category, ReviewState
from platform_db.models.platform_tables import UserRole
from platform_db.models.registry import Application, DataSource
from platform_db.models.scanning import (
    Finding, Inventory, ScanJob, Suppression,
)

from . import audit, db
from .auth import Principal, current_user
from .settings import settings


def _grant_owner(s, user: Principal, application_id) -> None:
    """Make the registering user the application Owner, so scoped reads show it to them."""
    s.add(UserRole(user_id=user.user_id, role=Role.OWNER, application_id=application_id))


def _assert_access(user: Principal, application_id) -> None:
    import uuid as _uuid
    if user.is_global:
        return
    if _uuid.UUID(str(application_id)) not in user.application_ids:
        raise HTTPException(status_code=404, detail="application not found")

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


class RegisterScanTarget(BaseModel):
    """Register a target application and its read-only database in one step.

    The admin provides the application name and the target's connection and read-only
    credentials. The password is encrypted at rest (never stored or returned in clear);
    ``presence_only`` (default true) records which columns hold which PII category, never
    a value.
    """

    name: str = Field(..., min_length=1, max_length=200)
    environment: Environment = Environment.PROD
    hosting: Hosting = Hosting.ON_PREM
    internet_facing: bool = False
    kind: DataSourceKind = DataSourceKind.POSTGRES
    host: str = Field(..., min_length=1)          # IP address or hostname
    port: int = 5432
    database: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    scan_profile: ScanProfile = ScanProfile.STANDARD
    presence_only: bool = True
    tags: list[str] = Field(default_factory=list)


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
def list_applications(user: Principal = Depends(current_user)) -> dict:
    with db.scoped_session(user) as s:            # RLS: only the caller's applications
        rows = s.query(Application).order_by(Application.created_at).all()
        return {"count": len(rows), "applications": [_app_dict(a) for a in rows]}


@router.post("/applications", status_code=201)
def register_application(body: RegisterApplication,
                         user: Principal = Depends(current_user)) -> dict:
    with db.get_sessionmaker()() as s:
        app = Application(
            name=body.name, description=body.description,
            environment=body.environment, hosting=body.hosting,
            internet_facing=body.internet_facing, user_base=body.user_base,
            approx_records=body.approx_records, lifecycle=body.lifecycle,
            tags=body.tags)
        s.add(app)
        s.flush()
        _grant_owner(s, user, app.id)
        s.commit()
        return _app_dict(app)


@router.get("/applications/{application_id}")
def get_application(application_id: uuid.UUID,
                    user: Principal = Depends(current_user)) -> dict:
    with db.scoped_session(user) as s:
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
def list_data_sources(application_id: uuid.UUID,
                      user: Principal = Depends(current_user)) -> dict:
    with db.scoped_session(user) as s:
        rows = s.query(DataSource).filter(
            DataSource.application_id == application_id).order_by(
            DataSource.created_at).all()
        return {"count": len(rows), "data_sources": [_source_dict(d) for d in rows]}


@router.post("/applications/{application_id}/data-sources", status_code=201)
def add_data_source(application_id: uuid.UUID, body: AddDataSource,
                    user: Principal = Depends(current_user)) -> dict:
    _assert_access(user, application_id)
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


# ── scan target registration + connectivity test ────────────────────────────
@router.post("/scan-targets", status_code=201)
def register_scan_target(body: RegisterScanTarget,
                         user: Principal = Depends(current_user)) -> dict:
    """Register a target application and its read-only database in one step.

    The read-only password is encrypted at rest and never returned; the stored
    connection holds only host/port/database/username and the presence-only flag.
    """
    connection = {
        "host": body.host, "port": body.port, "database": body.database,
        "username": body.username, "presence_only": body.presence_only,
    }
    try:
        credential_ref = crypto.encrypt_secret(body.password)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"credential vault unavailable: {e}")
    with db.get_sessionmaker()() as s:
        app = Application(
            name=body.name, environment=body.environment, hosting=body.hosting,
            internet_facing=body.internet_facing, lifecycle=Lifecycle.ACTIVE,
            tags=body.tags)
        s.add(app)
        s.flush()
        _grant_owner(s, user, app.id)
        ds = DataSource(
            application_id=app.id, kind=body.kind,
            display_name=f"{body.host}:{body.port}/{body.database}",
            connection=connection, credential_ref=credential_ref,
            scan_profile_default=body.scan_profile)
        s.add(ds)
        s.commit()
        return {
            "application_id": str(app.id), "data_source_id": str(ds.id),
            "application": _app_dict(app), "data_source": _source_dict(ds),
        }


@router.post("/data-sources/{data_source_id}/test")
def test_data_source(data_source_id: uuid.UUID) -> dict:
    """Connectivity test (FR-2.6): resolve the credential, open a read-only connection,
    and probe it. Never returns the credential."""
    with db.get_sessionmaker()() as s:
        ds = s.get(DataSource, data_source_id)
        if ds is None:
            raise HTTPException(status_code=404, detail="data source not found")
    from worker.factory import build_connector
    try:
        result = build_connector(ds).test()
        return {"ok": result.ok, "detail": result.detail}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": str(e)}


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
    user: Principal = Depends(current_user),
) -> dict:
    with db.scoped_session(user) as s:
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
def get_inventory(application_id: uuid.UUID,
                  user: Principal = Depends(current_user)) -> dict:
    with db.scoped_session(user) as s:
        rows = s.query(Inventory).filter(
            Inventory.application_id == application_id).order_by(
            Inventory.category).all()
        return {"count": len(rows), "inventory": [{
            "category": i.category.value, "tier": i.tier.value,
            "locations_count": i.locations_count, "rows_estimate": i.rows_estimate,
            "protection_state_summary": i.protection_state_summary or {},
            "purpose": i.purpose, "source_of_data": i.source_of_data,
            "recipients": i.recipients, "retention": i.retention,
        } for i in rows]}


# ── findings review workflow (FR-4.6) ────────────────────────────────────────
_REVIEW_ACTIONS = {"confirm", "false_positive", "reclassify", "suppress"}


class ReviewAction(BaseModel):
    """A reviewer's verdict on a finding (SRS FR-4.6)."""

    action: str                              # confirm|false_positive|reclassify|suppress
    new_category: Category | None = None     # required when action == reclassify
    reason: str | None = None                # suppression reason / note
    suppress_scope: str = "column"           # column|table|path — granularity of a suppression


class BulkReview(ReviewAction):
    finding_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=1000)


def _suppression_match(locator: dict, scope: str) -> dict:
    """The locator subset a suppression keys on, at the chosen granularity. A finding
    is suppressed when its locator CONTAINS this subset (and the category matches).

    The scope is interpreted against the locator shape: a database finding keys on
    schema/table/column, a file finding on path/line. ``table``/``path`` scope means
    the whole container (table, or file path). Null components are dropped, and the
    match NEVER comes back empty (an empty match would suppress everything) — it falls
    back to the exact location."""
    is_file = locator.get("path") is not None
    if scope == "path":
        keys = ("path",) if is_file else ("schema", "table")
    elif scope == "table":
        keys = ("path",) if is_file else ("schema", "table")
    else:  # exact location (default)
        keys = ("path", "line") if is_file else ("schema", "table", "column")
    match = {k: locator[k] for k in keys if locator.get(k) is not None}
    if not match:  # never suppress everything by accident
        exact = ("path", "line") if is_file else ("schema", "table", "column")
        match = {k: locator[k] for k in exact if locator.get(k) is not None}
    return match


def _matches(locator: dict, locator_match: dict) -> bool:
    """True when every key/value in ``locator_match`` is present in ``locator``."""
    return all(locator.get(k) == v for k, v in (locator_match or {}).items())


def _apply_review(s, user: Principal, finding: Finding, body: ReviewAction) -> dict:
    """Mutate one finding per the reviewer's action; create a suppression when asked.
    Returns the serialised new state. Caller owns the transaction + audit."""
    before = {"review_state": finding.review_state.value,
              "category": finding.category.value}
    finding.reviewed_by = user.user_id
    finding.reviewed_at = text("now()")
    if body.action == "confirm":
        finding.review_state = ReviewState.CONFIRMED
    elif body.action == "false_positive":
        finding.review_state = ReviewState.FALSE_POSITIVE
    elif body.action == "reclassify":
        if body.new_category is None:
            raise HTTPException(status_code=400, detail="reclassify requires new_category")
        finding.review_state = ReviewState.RECLASSIFIED
        finding.category = body.new_category
    elif body.action == "suppress":
        finding.review_state = ReviewState.SUPPRESSED
        sup = Suppression(
            application_id=finding.application_id,
            locator_match=_suppression_match(finding.locator or {}, body.suppress_scope),
            category=finding.category, reason=body.reason, created_by=user.user_id)
        s.add(sup)
        s.flush()
        finding.suppression_id = sup.id
    else:
        raise HTTPException(status_code=400,
                            detail=f"action must be one of {sorted(_REVIEW_ACTIONS)}")
    after = {"review_state": finding.review_state.value,
             "category": finding.category.value}
    audit.record(s, actor_id=user.user_id, action=f"finding.{body.action}",
                 object_type="finding", object_id=str(finding.id),
                 before=before, after=after)
    return after


@router.post("/findings/{finding_id}/review")
def review_finding(finding_id: uuid.UUID, body: ReviewAction,
                   user: Principal = Depends(current_user)) -> dict:
    with db.get_sessionmaker()() as s:
        finding = s.query(Finding).filter(Finding.id == finding_id).first()
        if finding is None:
            raise HTTPException(status_code=404, detail="finding not found")
        _assert_access(user, finding.application_id)
        after = _apply_review(s, user, finding, body)
        s.commit()
        return {"id": str(finding_id), **after}


@router.post("/applications/{application_id}/findings/review")
def review_findings_bulk(application_id: uuid.UUID, body: BulkReview,
                         user: Principal = Depends(current_user)) -> dict:
    _assert_access(user, application_id)
    with db.get_sessionmaker()() as s:
        rows = s.query(Finding).filter(
            Finding.application_id == application_id,
            Finding.id.in_(body.finding_ids)).all()
        for f in rows:
            _apply_review(s, user, f, body)
        s.commit()
        return {"reviewed": len(rows), "action": body.action}


# ── suppressions (persist across scans) ──────────────────────────────────────
class CreateSuppression(BaseModel):
    locator_match: dict = Field(default_factory=dict)
    category: Category | None = None
    reason: str | None = None


@router.get("/applications/{application_id}/suppressions")
def list_suppressions(application_id: uuid.UUID,
                      user: Principal = Depends(current_user)) -> dict:
    with db.scoped_session(user) as s:
        rows = s.query(Suppression).filter(
            Suppression.application_id == application_id).order_by(
            Suppression.created_at.desc()).all()
        return {"count": len(rows), "suppressions": [{
            "id": str(x.id), "locator_match": x.locator_match,
            "category": x.category.value if x.category else None,
            "reason": x.reason,
            "created_at": x.created_at.isoformat() if x.created_at else None,
        } for x in rows]}


@router.post("/applications/{application_id}/suppressions", status_code=201)
def create_suppression(application_id: uuid.UUID, body: CreateSuppression,
                       user: Principal = Depends(current_user)) -> dict:
    _assert_access(user, application_id)
    with db.get_sessionmaker()() as s:
        sup = Suppression(application_id=application_id, locator_match=body.locator_match,
                          category=body.category, reason=body.reason,
                          created_by=user.user_id)
        s.add(sup)
        s.flush()
        audit.record(s, actor_id=user.user_id, action="suppression.create",
                     object_type="suppression", object_id=str(sup.id),
                     after={"locator_match": body.locator_match,
                            "category": body.category.value if body.category else None})
        s.commit()
        return {"id": str(sup.id)}


@router.delete("/suppressions/{suppression_id}", status_code=204)
def delete_suppression(suppression_id: uuid.UUID,
                       user: Principal = Depends(current_user)) -> None:
    with db.get_sessionmaker()() as s:
        sup = s.get(Suppression, suppression_id)
        if sup is None:
            raise HTTPException(status_code=404, detail="suppression not found")
        _assert_access(user, sup.application_id)
        audit.record(s, actor_id=user.user_id, action="suppression.delete",
                     object_type="suppression", object_id=str(sup.id),
                     before={"locator_match": sup.locator_match})
        s.delete(sup)
        s.commit()


# ── editable data-inventory matrix (purpose/source/recipients/retention) ──────
class InventoryEdit(BaseModel):
    purpose: str | None = None
    source_of_data: str | None = None
    recipients: str | None = None
    retention: str | None = None


@router.put("/applications/{application_id}/inventory/{category}")
def edit_inventory(application_id: uuid.UUID, category: str, body: InventoryEdit,
                   user: Principal = Depends(current_user)) -> dict:
    _assert_access(user, application_id)
    with db.get_sessionmaker()() as s:
        row = s.query(Inventory).filter(
            Inventory.application_id == application_id,
            Inventory.category == category).first()
        if row is None:
            raise HTTPException(status_code=404, detail="inventory row not found")
        before = {"purpose": row.purpose, "source_of_data": row.source_of_data,
                  "recipients": row.recipients, "retention": row.retention}
        row.purpose = body.purpose
        row.source_of_data = body.source_of_data
        row.recipients = body.recipients
        row.retention = body.retention
        after = {"purpose": row.purpose, "source_of_data": row.source_of_data,
                 "recipients": row.recipients, "retention": row.retention}
        audit.record(s, actor_id=user.user_id, action="inventory.update",
                     object_type="inventory", object_id=f"{application_id}/{category}",
                     before=before, after=after)
        s.commit()
        return {"category": category, **after}


# ── portfolio dashboard ──────────────────────────────────────────────────────
@router.get("/dashboard/portfolio")
def portfolio(user: Principal = Depends(current_user)) -> dict:
    """Aggregate for the dashboard: per-application category coverage + top tier,
    portfolio totals, and a scan-coverage gauge — scoped to the caller's applications."""
    _TIER_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    with db.scoped_session(user) as s:
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
