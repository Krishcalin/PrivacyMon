"""Scan pipeline (SRS 3.3 / 7.2): run a connector and persist its findings.

The worker is the TRUSTED writer — it connects as the database owner, so it may
create a per-job ``findings`` partition and write rows for whichever application it
was asked to scan. Row-level security protects the READ path (the API, as a scoped
role); it is not the worker's job to enforce it, so the worker is not subject to it.

A scan: open a job → create its findings partition → enumerate units → scan each
into ``dpia_core`` findings → persist → rebuild the inventory → compute inherent risk
→ close the job. Synchronous and transaction-safe so it runs the same way under a
Celery task or a direct call; the Celery wrapper lives in ``worker.tasks``.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import text
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
    """Run ``connector`` and persist a complete scan for one data source."""
    clock = now or (lambda: int(time.time()))
    job = ScanJob(
        data_source_id=data_source_id, application_id=application_id,
        profile=profile, state=ScanState.RUNNING, triggered_by=triggered_by)
    session.add(job)
    session.flush()                      # assign job.id before we partition/insert on it

    # One partition per job (SRS 8.2): a retention sweep later DETACHES it instead of
    # deleting millions of rows. Created by the owner connection the worker holds.
    session.execute(text(
        f'CREATE TABLE IF NOT EXISTS "{_partition_name(job.id)}" '
        f"PARTITION OF findings FOR VALUES IN ('{job.id}')"))

    units_total = 0
    findings_total = 0
    for unit in connector.enumerate():
        units_total += 1
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
        findings_total += len(findings)
        su.state = ScanState.COMPLETED
        su.rows_sampled = 0
        su.duration_ms = max(0, (clock() - started) * 1000)

    session.flush()
    inventory = _rebuild_inventory(session, application_id, job.id)
    risk = _inherent_risk(session, application_id, inventory)

    job.state = ScanState.COMPLETED
    job.units_total = units_total
    job.units_done = units_total
    job.findings_count = findings_total
    job.finished_at = text("now()")
    session.commit()

    return {
        "job_id": str(job.id),
        "state": job.state.value,
        "units": units_total,
        "findings": findings_total,
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
