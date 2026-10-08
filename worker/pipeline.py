"""Scan pipeline (SRS 3.3 / 7.2): run a connector and persist its findings, with
live progress and pause/resume/cancel.

The worker is the TRUSTED writer — it connects as the database owner, so it may
create a per-job ``findings`` partition and write rows for whichever application it
was asked to scan. Row-level security protects the READ path (the API, as a scoped
role); the worker is deliberately not subject to it.

Progress is committed per unit (``units_done`` / ``findings_count`` and each
``scan_units`` row), so the SSE endpoint can stream real progress and a paused or
cancelled scan keeps its partial results (SRS FR-3.3 / FR-3.6). Control is a
re-read of ``scan_jobs.state`` between units: the API sets ``paused`` or ``cancelled``
and the worker stops at the next boundary; a resumed job skips the units it already
finished, so resuming never double-writes.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from dpia_core import risk as risk_engine
from dpia_core.models import ScanProfile, Tier
from platform_db.enums import ScanState
from platform_db.models.registry import Application
from platform_db.models.scanning import Finding as FindingRow
from platform_db.models.scanning import Inventory, ScanJob, ScanUnit
from worker.connectors.base import Connector

_TIER_RANK = {Tier.LOW: 0, Tier.MEDIUM: 1, Tier.HIGH: 2, Tier.CRITICAL: 3}
_STOP_STATES = {ScanState.PAUSED, ScanState.CANCELLED}


def _partition_name(job_id: uuid.UUID) -> str:
    return f"findings_p_{job_id.hex}"


def run_scan(
    session: Session,
    *,
    application_id: uuid.UUID,
    data_source_id: uuid.UUID,
    connector: Connector,
    profile: ScanProfile = ScanProfile.STANDARD,
    triggered_by: uuid.UUID | None = None,
    now=None,
) -> dict[str, Any]:
    """Create a job and run it to completion — the direct/synchronous entry point."""
    job = ScanJob(
        data_source_id=data_source_id, application_id=application_id,
        profile=profile, state=ScanState.QUEUED, triggered_by=triggered_by)
    session.add(job)
    session.commit()
    return run_job(session, job.id, connector, now=now)


def run_job(session: Session, job_id: uuid.UUID, connector: Connector, *, now=None
            ) -> dict[str, Any]:
    """Run (or resume) an already-created job by id. Idempotent to resume."""
    clock = now or (lambda: int(time.time()))
    job = session.get(ScanJob, job_id)
    if job is None:
        raise ValueError(f"scan job {job_id} not found")
    # Do not (re)start a job that is already cancelled or finished — e.g. the API
    # cancelled it while it sat queued. A resume sets the job back to QUEUED first, so
    # a genuine resume never lands here.
    if job.state in (ScanState.CANCELLED, ScanState.COMPLETED, ScanState.FAILED):
        return _summary(job_id, job.state.value, job.units_done or 0,
                        job.findings_count or 0, inventory={}, risk=None)
    application_id = job.application_id
    data_source_id = job.data_source_id

    job.state = ScanState.RUNNING
    if job.started_at is None:
        job.started_at = text("now()")
    session.execute(text(
        f'CREATE TABLE IF NOT EXISTS "{_partition_name(job.id)}" '
        f"PARTITION OF findings FOR VALUES IN ('{job.id}')"))
    session.commit()

    # Resume support: units already completed in a prior run are skipped, so a
    # resumed scan never re-writes their findings (SRS FR-3.6, "partial results kept").
    done = {loc for (loc,) in session.execute(
        select(ScanUnit.locator).where(
            ScanUnit.scan_job_id == job.id,
            ScanUnit.state == ScanState.COMPLETED)).all()}

    units = list(connector.enumerate())
    job.units_total = len(units)
    session.commit()

    units_done = len(done)
    findings_total = job.findings_count or 0
    stopped_state: ScanState | None = None

    for unit in units:
        current = session.execute(
            select(ScanJob.state).where(ScanJob.id == job.id)).scalar()
        if current in _STOP_STATES:                  # API requested pause/cancel
            stopped_state = current
            break
        if unit.key in done:
            continue
        started = clock()
        su = ScanUnit(scan_job_id=job.id, kind=unit.kind, locator=unit.key,
                      state=ScanState.RUNNING)
        session.add(su)
        session.flush()
        findings = connector.scan_unit(unit)
        for f in findings:
            session.add(FindingRow(
                scan_job_id=job.id, application_id=application_id,
                data_source_id=data_source_id, unit_id=su.id,
                category=f.category, tier=f.tier,
                confidence=round(f.confidence, 3), hit_rate=round(f.hit_rate, 3),
                locator=f.locator.as_dict(), protection_state=f.protection_state,
                combined_identity=f.combined_identity, evidence=list(f.evidence)[:3],
                pack_version=f.pack_version or None))
        su.state = ScanState.COMPLETED
        su.duration_ms = max(0, (clock() - started) * 1000)
        units_done += 1
        findings_total += len(findings)
        job.units_done = units_done
        job.findings_count = findings_total
        session.commit()                             # progress visible + partial kept

    if stopped_state is not None:
        if stopped_state == ScanState.CANCELLED:
            job.finished_at = text("now()")
            session.commit()
        return _summary(job_id, stopped_state.value, units_done, findings_total,
                        inventory={}, risk=None)

    inventory = _rebuild_inventory(session, application_id, job.id)
    risk = _inherent_risk(session, application_id, inventory)
    job.state = ScanState.COMPLETED
    job.units_done = units_done
    job.findings_count = findings_total
    job.finished_at = text("now()")
    session.commit()
    return _summary(job_id, ScanState.COMPLETED.value, units_done, findings_total,
                    inventory=inventory, risk=risk)


def _summary(job_id, state, units, findings, *, inventory, risk) -> dict[str, Any]:
    return {
        "job_id": str(job_id), "state": state, "units": units, "findings": findings,
        "inventory": {c: v["locations_count"] for c, v in inventory.items()},
        "inherent_risk": risk,
    }


def _rebuild_inventory(session: Session, application_id: uuid.UUID,
                       job_id: uuid.UUID) -> dict[str, dict]:
    """One row per application x category from this job's findings (SRS 8.2).

    Owner-annotated columns (purpose, source_of_data, recipients) are preserved:
    the upsert updates only the computed fields on conflict.
    """
    rows = session.query(FindingRow).filter(
        FindingRow.scan_job_id == job_id,
        FindingRow.application_id == application_id).all()

    agg: dict[str, dict] = defaultdict(lambda: {
        "tier": Tier.LOW, "locations": set(), "protection": defaultdict(int)})
    for r in rows:
        cat = r.category.value if hasattr(r.category, "value") else r.category
        a = agg[cat]
        tier = r.tier if hasattr(r.tier, "value") else Tier(r.tier)
        if _TIER_RANK[tier] > _TIER_RANK[a["tier"]]:
            a["tier"] = tier
        loc = r.locator or {}
        a["locations"].add((loc.get("path"), loc.get("table"), loc.get("column"),
                            loc.get("line")))
        ps = r.protection_state.value if hasattr(r.protection_state, "value") \
            else r.protection_state
        a["protection"][ps] += 1

    out: dict[str, dict] = {}
    for cat, a in agg.items():
        locations_count = len(a["locations"])
        out[cat] = {"tier": a["tier"], "locations_count": locations_count,
                    "protection": dict(a["protection"])}
        stmt = pg_insert(Inventory.__table__).values(
            application_id=application_id, category=cat, tier=a["tier"].value,
            locations_count=locations_count, rows_estimate=locations_count,
            protection_state_summary=dict(a["protection"]),
            computed_at=text("now()"))
        stmt = stmt.on_conflict_do_update(
            constraint="uq_inventory_application_id_category",
            set_={"tier": a["tier"].value, "locations_count": locations_count,
                  "rows_estimate": locations_count,
                  "protection_state_summary": dict(a["protection"]),
                  "computed_at": text("now()"), "updated_at": text("now()")})
        session.execute(stmt)
    session.flush()
    return out


def _inherent_risk(session: Session, application_id: uuid.UUID,
                   inventory: dict[str, dict]) -> dict:
    """Inherent risk from the rebuilt inventory and the application's exposure (SRS 5.3)."""
    app = session.get(Application, application_id)
    plain_hi = any(
        inv["protection"].get("plain", 0) > 0 and inv["tier"] in (Tier.HIGH, Tier.CRITICAL)
        for inv in inventory.values())
    user_base = getattr(app, "user_base", None)
    external = bool(user_base) and getattr(user_base, "value", user_base) in (
        "customers", "public")
    exposure = risk_engine.ExposureInputs(
        internet_facing=bool(getattr(app, "internet_facing", False)),
        external_users=external,
        plain_high_or_critical=plain_hi)
    categories = [risk_engine.CategoryExposure(tier=inv["tier"],
                                               rows=inv["locations_count"])
                  for inv in inventory.values()]
    score = risk_engine.inherent_risk(categories, exposure)
    return {"score": round(score, 2), "band": risk_engine.band(score).value,
            "exposure_multiplier": round(risk_engine.exposure_multiplier(exposure), 3)}
