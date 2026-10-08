"""Scan control endpoints (SRS 9: start, status, pause/resume/cancel, SSE progress).

Starting a scan creates a ``QUEUED`` job then enqueues it. In ``celery`` mode the
worker processes it in the background and the request returns immediately; otherwise
(dev / no broker) the pipeline runs inline. Celery is imported lazily so the module
imports without the broker libraries. Progress is streamed by polling the job row the
worker updates per unit, and pause/resume/cancel flip the job state the worker reads.
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from platform_db.enums import ScanState
from platform_db.models.registry import DataSource
from platform_db.models.scanning import ScanJob

from . import db
from .settings import settings

router = APIRouter(prefix=settings.api_prefix)

_TERMINAL = {ScanState.COMPLETED.value, ScanState.FAILED.value, ScanState.CANCELLED.value}


def _job_dict(job: ScanJob) -> dict:
    return {
        "job_id": str(job.id),
        "application_id": str(job.application_id),
        "data_source_id": str(job.data_source_id),
        "state": job.state.value,
        "profile": job.profile.value,
        "units_total": job.units_total,
        "units_done": job.units_done,
        "findings_count": job.findings_count,
    }


def _enqueue(job_id: uuid.UUID) -> str:
    """Hand the job to the worker (celery) or run it inline (dev / broker down)."""
    if settings.scan_mode == "celery":
        try:
            from worker.tasks import run_scan_task
            run_scan_task.delay(str(job_id))
            return "queued"
        except Exception:                            # noqa: BLE001 — fall back to inline
            pass
    from worker.factory import build_connector
    from worker.pipeline import run_job
    sessionmaker = db.get_sessionmaker()
    with sessionmaker() as s:
        job = s.get(ScanJob, job_id)
        data_source = s.get(DataSource, job.data_source_id)
        connector = build_connector(data_source, profile=job.profile)
        run_job(s, job_id, connector)
    return "completed"


@router.post("/data-sources/{data_source_id}/scans", status_code=202)
def start_scan(data_source_id: uuid.UUID) -> dict:
    sessionmaker = db.get_sessionmaker()
    with sessionmaker() as s:
        ds = s.get(DataSource, data_source_id)
        if ds is None:
            raise HTTPException(status_code=404, detail="data source not found")
        job = ScanJob(data_source_id=ds.id, application_id=ds.application_id,
                      profile=ds.scan_profile_default, state=ScanState.QUEUED)
        s.add(job)
        s.commit()
        job_id = job.id
    state = _enqueue(job_id)
    return {"job_id": str(job_id), "state": state}


@router.get("/scans/{job_id}")
def get_scan(job_id: uuid.UUID) -> dict:
    sessionmaker = db.get_sessionmaker()
    with sessionmaker() as s:
        job = s.get(ScanJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="scan not found")
        return _job_dict(job)


def _set_state(job_id: uuid.UUID, to: ScanState, allowed: set[ScanState]) -> dict:
    sessionmaker = db.get_sessionmaker()
    with sessionmaker() as s:
        job = s.get(ScanJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="scan not found")
        if job.state not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"cannot move a {job.state.value} scan to {to.value}")
        job.state = to
        s.commit()
        return _job_dict(job)


@router.post("/scans/{job_id}/pause")
def pause_scan(job_id: uuid.UUID) -> dict:
    return _set_state(job_id, ScanState.PAUSED, {ScanState.QUEUED, ScanState.RUNNING})


@router.post("/scans/{job_id}/cancel")
def cancel_scan(job_id: uuid.UUID) -> dict:
    return _set_state(job_id, ScanState.CANCELLED,
                      {ScanState.QUEUED, ScanState.RUNNING, ScanState.PAUSED})


@router.post("/scans/{job_id}/resume")
def resume_scan(job_id: uuid.UUID) -> dict:
    out = _set_state(job_id, ScanState.QUEUED, {ScanState.PAUSED})
    _enqueue(job_id)                                 # worker resumes, skipping done units
    return out


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/scans/{job_id}/events")
def scan_events(job_id: uuid.UUID, timeout: int = 120) -> StreamingResponse:
    """Server-Sent Events: emit a `progress` event whenever the job row changes, until
    it reaches a terminal state (SRS FR-3.3). Polls the row the worker commits per unit."""
    def gen():
        sessionmaker = db.get_sessionmaker()
        last = None
        deadline = time.time() + max(1, min(timeout, 600))
        while time.time() < deadline:
            with sessionmaker() as s:
                job = s.get(ScanJob, job_id)
                if job is None:
                    yield _sse("error", {"detail": "scan not found"})
                    return
                snap = _job_dict(job)
            if snap != last:
                yield _sse("progress", snap)
                last = snap
            if snap["state"] in _TERMINAL:
                return
            time.sleep(1)
        yield _sse("timeout", {"job_id": str(job_id)})
    return StreamingResponse(gen(), media_type="text/event-stream")
