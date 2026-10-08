"""Continuous-monitoring API (SRS FR-3.1 / FR-4.x): schedule a data source, review the
change-event timeline, and manage notification webhooks.

Reads are RLS-scoped to the caller's applications; writes use the owner session gated by
``_assert_access`` (the established console pattern), and every write is audited.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from platform_db import crypto
from platform_db.models.platform_tables import Webhook
from platform_db.models.registry import DataSource
from platform_db.models.scanning import ChangeEvent

from . import audit, db
from .auth import Principal, current_user, require_global
from .console import _assert_access
from .settings import settings
from worker.monitoring import cron_due  # pure helper, no broker import

router = APIRouter(prefix=settings.api_prefix)


# ── schedule a data source ────────────────────────────────────────────────────
class SetSchedule(BaseModel):
    schedule_cron: str | None = Field(default=None, max_length=100)


def _validate_cron(expr: str | None) -> None:
    if expr is None or not expr.strip():
        return
    if len(expr.split()) != 5:
        raise HTTPException(status_code=400,
                            detail="cron must have 5 fields: minute hour dom month dow")
    # A syntactically valid expression evaluates without raising for a sample instant.
    from datetime import datetime, timezone
    try:
        cron_due(expr, datetime.now(timezone.utc))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid cron expression")


@router.put("/data-sources/{data_source_id}/schedule")
def set_schedule(data_source_id: uuid.UUID, body: SetSchedule,
                 user: Principal = Depends(current_user)) -> dict:
    _validate_cron(body.schedule_cron)
    with db.get_sessionmaker()() as s:
        ds = s.get(DataSource, data_source_id)
        if ds is None:
            raise HTTPException(status_code=404, detail="data source not found")
        _assert_access(user, ds.application_id)
        before = {"schedule_cron": ds.schedule_cron}
        ds.schedule_cron = body.schedule_cron.strip() if body.schedule_cron else None
        audit.record(s, actor_id=user.user_id, action="data_source.schedule",
                     object_type="data_source", object_id=str(ds.id),
                     before=before, after={"schedule_cron": ds.schedule_cron})
        s.commit()
        return {"data_source_id": str(ds.id), "schedule_cron": ds.schedule_cron}


# ── change-event timeline ─────────────────────────────────────────────────────
@router.get("/applications/{application_id}/changes")
def list_changes(application_id: uuid.UUID, limit: int = 100,
                 user: Principal = Depends(current_user)) -> dict:
    with db.scoped_session(user) as s:
        rows = s.query(ChangeEvent).filter(
            ChangeEvent.application_id == application_id).order_by(
            ChangeEvent.at.desc()).limit(min(limit, 500)).all()
        return {"count": len(rows), "changes": [{
            "id": str(c.id), "at": c.at.isoformat() if c.at else None,
            "severity": c.severity, "summary": c.summary, "delta": c.delta,
            "acknowledged": c.acknowledged,
            "scan_job_id": str(c.scan_job_id) if c.scan_job_id else None,
        } for c in rows]}


@router.post("/changes/{change_id}/acknowledge")
def acknowledge_change(change_id: uuid.UUID,
                       user: Principal = Depends(current_user)) -> dict:
    with db.get_sessionmaker()() as s:
        c = s.get(ChangeEvent, change_id)
        if c is None:
            raise HTTPException(status_code=404, detail="change event not found")
        _assert_access(user, c.application_id)
        c.acknowledged = True
        audit.record(s, actor_id=user.user_id, action="change.acknowledge",
                     object_type="change_event", object_id=str(c.id))
        s.commit()
        return {"id": str(c.id), "acknowledged": True}


# ── notification webhooks (platform admin) ────────────────────────────────────
class CreateWebhook(BaseModel):
    url: str = Field(..., min_length=1)
    event_types: list[str] = Field(default_factory=lambda: ["inventory.changed"])
    secret: str | None = None
    active: bool = True


@router.get("/admin/webhooks")
def list_webhooks(_admin: Principal = Depends(require_global("admin"))) -> dict:
    with db.get_sessionmaker()() as s:
        rows = s.query(Webhook).order_by(Webhook.created_at.desc()).all()
        return {"count": len(rows), "webhooks": [{
            "id": str(w.id), "url": w.url, "event_types": list(w.event_types or []),
            "active": w.active, "has_secret": bool(w.secret_ref),
        } for w in rows]}


@router.post("/admin/webhooks", status_code=201)
def create_webhook(body: CreateWebhook,
                   admin: Principal = Depends(require_global("admin"))) -> dict:
    with db.get_sessionmaker()() as s:
        w = Webhook(url=body.url, event_types=body.event_types, active=body.active,
                    secret_ref=crypto.encrypt_secret(body.secret) if body.secret else None)
        s.add(w)
        s.flush()
        audit.record(s, actor_id=admin.user_id, action="webhook.create",
                     object_type="webhook", object_id=str(w.id),
                     after={"url": body.url, "event_types": body.event_types})
        s.commit()
        return {"id": str(w.id)}


@router.delete("/admin/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: uuid.UUID,
                   admin: Principal = Depends(require_global("admin"))) -> None:
    with db.get_sessionmaker()() as s:
        w = s.get(Webhook, webhook_id)
        if w is None:
            raise HTTPException(status_code=404, detail="webhook not found")
        audit.record(s, actor_id=admin.user_id, action="webhook.delete",
                     object_type="webhook", object_id=str(w.id), before={"url": w.url})
        s.delete(w)
        s.commit()
