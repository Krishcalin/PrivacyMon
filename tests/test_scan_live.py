"""Live integration tests against a real PostgreSQL (SRS FR-2.3, 3.3, 7.2, 8).

Skipped unless ``PRIVACYMON_TEST_DB`` is set to a target the baseline migration has
been applied to. Run them with the dev stack up:

    docker compose -f infra/docker-compose.yml up -d postgres
    PRIVACYMON_DB_URL=postgresql://privacymon:privacymon@localhost:5440/privacymon \
        python -m alembic upgrade head
    PRIVACYMON_TEST_DB=postgresql://privacymon:privacymon@localhost:5440/privacymon \
        python -m pytest tests/test_scan_live.py

They exercise what the structural tests cannot: a read-only scan of a target schema,
and the pipeline persisting findings into a per-job partition with inventory + risk.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

DSN = os.getenv("PRIVACYMON_TEST_DB")
pytestmark = pytest.mark.skipif(not DSN, reason="set PRIVACYMON_TEST_DB to run live DB tests")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_REPO = os.path.join(ROOT, "fixtures", "repo")


def _cleanup(engine, app_id: uuid.UUID, job_id: str | None) -> None:
    with engine.begin() as conn:
        if job_id:
            conn.execute(text(f'DROP TABLE IF EXISTS "findings_p_{uuid.UUID(job_id).hex}"'))
        conn.execute(text("DELETE FROM scan_units WHERE scan_job_id IN "
                          "(SELECT id FROM scan_jobs WHERE application_id=:a)"),
                     {"a": str(app_id)})
        for tbl in ("inventory", "scan_jobs", "data_sources"):
            conn.execute(text(f"DELETE FROM {tbl} WHERE application_id=:a"), {"a": str(app_id)})
        conn.execute(text("DELETE FROM applications WHERE id=:a"), {"a": str(app_id)})


def test_pipeline_persists_git_findings_with_inventory_and_risk():
    from dpia_core.models import ScanProfile
    from platform_db.enums import DataSourceKind, Environment, Hosting, Lifecycle, UserBase
    from platform_db.models.registry import Application, DataSource
    from platform_db.session import make_sync_engine, make_sync_sessionmaker
    from worker.connectors.git import GitConnector
    from worker.pipeline import run_scan

    engine = make_sync_engine(DSN)
    Session = make_sync_sessionmaker(engine)
    app_id, ds_id = uuid.uuid4(), uuid.uuid4()
    summary = None
    with Session() as s:
        s.add(Application(id=app_id, name="Live Test App", environment=Environment.PROD,
                          hosting=Hosting.CLOUD, internet_facing=True,
                          user_base=UserBase.CUSTOMERS, lifecycle=Lifecycle.ACTIVE, tags=[]))
        s.add(DataSource(id=ds_id, application_id=app_id, kind=DataSourceKind.GIT,
                         display_name="repo", connection={"path": FIXTURE_REPO}))
        s.commit()
    try:
        with Session() as s:
            summary = run_scan(s, application_id=app_id, data_source_id=ds_id,
                               connector=GitConnector(FIXTURE_REPO),
                               profile=ScanProfile.STANDARD)
        assert summary["state"] == "completed"
        assert summary["findings"] > 0 and summary["units"] == 2
        assert summary["inherent_risk"]["band"] in {"low", "medium", "high", "very_high"}
        with Session() as s:
            n = s.execute(text("SELECT count(*) FROM findings WHERE application_id=:a"),
                          {"a": str(app_id)}).scalar()
            inv = s.execute(text("SELECT count(*) FROM inventory WHERE application_id=:a"),
                            {"a": str(app_id)}).scalar()
        assert n == summary["findings"] and inv > 0
    finally:
        _cleanup(engine, app_id, summary["job_id"] if summary else None)


def test_postgres_connector_scans_a_target_schema_read_only():
    import psycopg

    from worker.connectors.postgres import PostgresConnector

    with psycopg.connect(DSN) as conn:
        conn.autocommit = True
        conn.execute("CREATE SCHEMA IF NOT EXISTS pii_live_test")
        conn.execute("DROP TABLE IF EXISTS pii_live_test.customers")
        conn.execute("CREATE TABLE pii_live_test.customers "
                     "(id serial primary key, email text, pan_no text, mobile text)")
        conn.execute("INSERT INTO pii_live_test.customers (email, pan_no, mobile) VALUES "
                     "('ananya.roy@example.com','ABCPK1234L','9876543210'),"
                     "('rahul.verma@example.com','AAAPL1234C','9123456780')")
    try:
        c = PostgresConnector(DSN)
        assert c.test().ok is True
        units = [u for u in c.enumerate() if u.meta["schema"] == "pii_live_test"]
        assert [u.key for u in units] == ["pii_live_test.customers"]
        findings = []
        for u in units:
            findings.extend(c.scan_unit(u))
        cats = {f.category.value for f in findings}
        assert {"email", "pan", "mobile"} <= cats
        for f in findings:
            assert f.locator.kind == "database" and f.locator.table == "customers"
    finally:
        with psycopg.connect(DSN) as conn:
            conn.autocommit = True
            conn.execute("DROP SCHEMA IF EXISTS pii_live_test CASCADE")
