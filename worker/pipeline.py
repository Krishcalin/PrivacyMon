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
from platform_db.enums import DpiaState, ReviewState, ScanState
from platform_db.models.assessment import DpiaAssessment
from platform_db.models.registry import Application, DataSource
from platform_db.models.scanning import ChangeEvent
from platform_db.models.scanning import Finding as FindingRow
from platform_db.models.scanning import Inventory, ScanJob, ScanUnit, Suppression
from worker import monitoring, notify
from worker.connectors.base import Connector

_TIER_RANK = {Tier.LOW: 0, Tier.MEDIUM: 1, Tier.HIGH: 2, Tier.CRITICAL: 3}
_STOP_STATES = {ScanState.PAUSED, ScanState.CANCELLED}


def _partition_name(job_id: uuid.UUID) -> str:
    return f"findings_p_{job_id.hex}"


def _load_suppressions(session: Session, application_id: uuid.UUID) -> list[Suppression]:
    """Active (non-expired) suppressions for an application — loaded once per scan so a
    reviewer's suppression persists across future scans (SRS FR-4.6)."""
    rows = session.execute(
        select(Suppression).where(Suppression.application_id == application_id)).scalars().all()
    now = time.time()
    active = []
    for s in rows:
        if s.expires_at is not None and s.expires_at.timestamp() <= now:
            continue
        active.append(s)
    return active


def _suppressed_by(locator: dict, category, suppressions: list[Suppression]):
    """Return the first suppression whose locator subset is contained in ``locator`` and
    whose category matches (or is unset, meaning any category at that locator)."""
    for s in suppressions:
        if s.category is not None and s.category != category:
            continue
        match = s.locator_match or {}
        if all(locator.get(k) == v for k, v in match.items()):
            return s
    return None


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

    # Load active suppressions once; a matching finding is written already suppressed,
    # so a reviewer's decision carries across every future scan (SRS FR-4.6).
    suppressions = _load_suppressions(session, application_id)

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
            locator = f.locator.as_dict()
            sup = _suppressed_by(locator, f.category, suppressions)
            session.add(FindingRow(
                scan_job_id=job.id, application_id=application_id,
                data_source_id=data_source_id, unit_id=su.id,
                category=f.category, tier=f.tier,
                confidence=round(f.confidence, 3), hit_rate=round(f.hit_rate, 3),
                locator=locator, protection_state=f.protection_state,
                combined_identity=f.combined_identity, evidence=list(f.evidence)[:3],
                pack_version=f.pack_version or None,
                review_state=ReviewState.SUPPRESSED if sup else ReviewState.NEW,
                suppression_id=sup.id if sup else None))
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

    # Capture the inventory as it stood BEFORE this scan's rebuild, so change detection
    # compares like with like (the previous scan's view of the same application).
    previous_inventory = _snapshot_inventory(session, application_id)
    inventory = _rebuild_inventory(session, application_id, job.id)
    risk = _inherent_risk(session, application_id, inventory)
    job.state = ScanState.COMPLETED
    job.units_done = units_done
    job.findings_count = findings_total
    job.finished_at = text("now()")
    session.commit()

    detect_and_flag_changes(session, application_id, data_source_id, job.id,
                            previous_inventory, inventory)
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

    Owner-annotated columns (purpose, source_of_data, recipients, retention) are
    preserved: the upsert updates only the computed fields on conflict. Findings a
    reviewer marked suppressed or false-positive are excluded from the data map.
    """
    rows = session.query(FindingRow).filter(
        FindingRow.scan_job_id == job_id,
        FindingRow.application_id == application_id,
        FindingRow.review_state.notin_(
            (ReviewState.SUPPRESSED, ReviewState.FALSE_POSITIVE))).all()

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


def _snapshot_inventory(session: Session, application_id: uuid.UUID) -> dict[str, dict]:
    """The application's inventory as it stands now — {category: {tier, locations_count}}.
    Read before a rebuild so change detection compares the prior scan to the new one."""
    rows = session.query(Inventory).filter(
        Inventory.application_id == application_id).all()
    return {r.category.value: {"tier": r.tier.value,
                               "locations_count": r.locations_count} for r in rows}


def detect_and_flag_changes(session: Session, application_id: uuid.UUID,
                            data_source_id: uuid.UUID | None, job_id: uuid.UUID,
                            previous: dict, current: dict) -> dict | None:
    """Compare the previous and current inventory; on a material change record a
    ``change_events`` row, flag the application's non-draft DPIAs for re-review, and
    dispatch notifications. Also advance the data source's ``last_scan_job_id``. Returns
    the delta dict when a change was recorded, else None. Never raises."""
    try:
        if data_source_id is not None:
            ds = session.get(DataSource, data_source_id)
            if ds is not None:
                ds.last_scan_job_id = job_id

        # The first scan of an application has no prior inventory — nothing to diff.
        if not previous:
            session.commit()
            return None

        delta = monitoring.diff_inventory(previous, current)
        if not monitoring.is_material(delta):
            session.commit()
            return None

        summary = _summarise_delta(delta)
        severity = "high" if delta.new_critical else "medium"
        session.add(ChangeEvent(
            application_id=application_id, data_source_id=data_source_id,
            scan_job_id=job_id, severity=severity, summary=summary,
            delta=delta.as_dict()))

        # Flag every non-draft DPIA for this application: its snapshot is now stale.
        flagged = session.query(DpiaAssessment).filter(
            DpiaAssessment.application_id == application_id,
            DpiaAssessment.state != DpiaState.DRAFT,
            DpiaAssessment.needs_review.is_(False)).all()
        for d in flagged:
            d.needs_review = True
        session.commit()

        _notify_change(session, application_id, summary, severity, delta, len(flagged))
        return delta.as_dict()
    except Exception:  # noqa: BLE001 — monitoring must never fail a completed scan
        session.rollback()
        return None


def _summarise_delta(delta) -> str:
    bits = []
    if delta.new_categories:
        bits.append(f"{len(delta.new_categories)} new categor"
                    f"{'y' if len(delta.new_categories) == 1 else 'ies'} "
                    f"({', '.join(delta.new_categories)})")
    if delta.escalated:
        bits.append(f"{len(delta.escalated)} tier escalation(s)")
    if delta.new_critical:
        bits.append(f"new high/critical data: {', '.join(delta.new_critical)}")
    if delta.grew:
        bits.append(f"{len(delta.grew)} category spread(s)")
    if delta.removed_categories:
        bits.append(f"{len(delta.removed_categories)} categor"
                    f"{'y' if len(delta.removed_categories) == 1 else 'ies'} no longer found")
    return "; ".join(bits) or "inventory changed"


def _notify_change(session: Session, application_id: uuid.UUID, summary: str,
                   severity: str, delta, flagged: int) -> None:
    """Best-effort fan-out of a material change to webhooks and (optionally) email."""
    app = session.get(Application, application_id)
    app_name = getattr(app, "name", str(application_id))
    payload = {"application_id": str(application_id), "application": app_name,
               "severity": severity, "summary": summary,
               "dpias_flagged": flagged, "delta": delta.as_dict()}
    notify.deliver_webhooks(session, "inventory.changed", payload)
    if notify.smtp_configured():
        notify.send_email(
            subject=f"[PrivacyMon] {app_name}: {summary}",
            body=(f"A scan of {app_name} detected a material change in personal-data "
                  f"exposure.\n\n{summary}\n\n{flagged} DPIA(s) were flagged for "
                  f"re-review."),
            recipients=_notify_recipients(session))


def _notify_recipients(session: Session) -> list[str]:
    """Deployment-wide notification recipients from the settings table (key
    ``notify.emails``), falling back to an env list. Never raises."""
    import os
    try:
        from platform_db.models.platform_tables import Setting
        row = session.get(Setting, "notify.emails")
        if row and isinstance(row.value, dict) and row.value.get("to"):
            return list(row.value["to"])
    except Exception:  # noqa: BLE001
        pass
    env = os.getenv("PRIVACYMON_NOTIFY_EMAILS", "")
    return [e.strip() for e in env.split(",") if e.strip()]
