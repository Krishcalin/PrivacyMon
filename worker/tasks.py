"""Celery tasks for the scan worker (SRS 3.2, 7.2).

The task loads the job and its data source, builds the connector, and runs the
pipeline. It is thin on purpose: all the work (progress, control, resume, inventory,
risk) lives in ``worker.pipeline`` so a scan behaves identically whether driven by
Celery or called directly.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from worker.celery_app import celery_app


def _sessionmaker():
    from platform_db.session import make_sync_engine, make_sync_sessionmaker
    db_url = os.environ["PRIVACYMON_DB_URL"]
    return make_sync_sessionmaker(make_sync_engine(db_url))


@celery_app.task(name="privacymon.run_scan", bind=True)
def run_scan_task(self, job_id: str) -> dict:
    from platform_db.models.registry import DataSource
    from platform_db.models.scanning import ScanJob
    from worker.factory import build_connector
    from worker.pipeline import run_job

    from worker.detectors import effective_detectors

    Session = _sessionmaker()
    jid = uuid.UUID(job_id)
    with Session() as session:
        job = session.get(ScanJob, jid)
        if job is None:
            raise ValueError(f"scan job {job_id} not found")
        data_source = session.get(DataSource, job.data_source_id)
        detectors, pack_version = effective_detectors(session)
        connector = build_connector(data_source, profile=job.profile,
                                    detectors=detectors, pack_version=pack_version)
        return run_job(session, jid, connector)


@celery_app.task(name="privacymon.scheduled_scan_tick", bind=True)
def scheduled_scan_tick(self, now_iso: str | None = None) -> dict:
    """Celery-beat heartbeat (once a minute): enqueue a scan for every data source whose
    ``schedule_cron`` fires this minute (SRS FR-3.1). Idempotent per minute — a source
    already running or queued is skipped, so an overlapping tick never double-scans."""
    from platform_db.enums import ScanState
    from platform_db.models.registry import DataSource
    from platform_db.models.scanning import ScanJob
    from worker.monitoring import cron_due

    when = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    Session = _sessionmaker()
    enqueued: list[str] = []
    with Session() as session:
        sources = session.query(DataSource).filter(
            DataSource.schedule_cron.isnot(None)).all()
        for ds in sources:
            if not cron_due(ds.schedule_cron, when):
                continue
            # Skip if a scan for this source is already queued or running.
            busy = session.query(ScanJob).filter(
                ScanJob.data_source_id == ds.id,
                ScanJob.state.in_((ScanState.QUEUED, ScanState.RUNNING))).first()
            if busy is not None:
                continue
            job = ScanJob(data_source_id=ds.id, application_id=ds.application_id,
                          profile=ds.scan_profile_default, state=ScanState.QUEUED)
            session.add(job)
            session.commit()
            run_scan_task.delay(str(job.id))
            enqueued.append(str(job.id))
    return {"tick": when.isoformat(), "enqueued": enqueued}
