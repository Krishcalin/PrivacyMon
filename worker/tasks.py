"""Celery tasks for the scan worker (SRS 3.2, 7.2).

The task loads the job and its data source, builds the connector, and runs the
pipeline. It is thin on purpose: all the work (progress, control, resume, inventory,
risk) lives in ``worker.pipeline`` so a scan behaves identically whether driven by
Celery or called directly.
"""
from __future__ import annotations

import os
import uuid

from worker.celery_app import celery_app


@celery_app.task(name="privacymon.run_scan", bind=True)
def run_scan_task(self, job_id: str) -> dict:
    from platform_db.models.registry import DataSource
    from platform_db.models.scanning import ScanJob
    from platform_db.session import make_sync_engine, make_sync_sessionmaker
    from worker.factory import build_connector
    from worker.pipeline import run_job

    db_url = os.environ["PRIVACYMON_DB_URL"]
    engine = make_sync_engine(db_url)
    Session = make_sync_sessionmaker(engine)
    jid = uuid.UUID(job_id)
    with Session() as session:
        job = session.get(ScanJob, jid)
        if job is None:
            raise ValueError(f"scan job {job_id} not found")
        data_source = session.get(DataSource, job.data_source_id)
        connector = build_connector(data_source, profile=job.profile)
        return run_job(session, jid, connector)
