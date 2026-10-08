"""Tests for the platform persistence layer (SRS section 8).

Structural, not live: there is no PostgreSQL in this environment, so these assert the
model metadata, the generated DDL contract (RLS, audit trigger, partition, GIN), the
UUID v7 generator, and the RLS session-variable setter — everything the baseline
migration depends on — without connecting to a database.
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

import dpia_core.models as core
from platform_db import Base, ddl, enums
from platform_db.ids import uuid7
from platform_db.session import normalise_async_url, set_rls_context

PG = postgresql.dialect()

EXPECTED_TABLES = {
    "business_units", "applications", "data_sources",            # registry
    "detector_packs", "detectors", "scan_jobs", "scan_units",    # scanning
    "findings", "suppressions", "inventory", "change_events",
    "questionnaire_templates", "dpia_assessments",               # assessment
    "questionnaire_responses", "dpia_comments", "controls",
    "risks", "dpia_transitions", "dpia_records",
    "users", "user_roles", "api_tokens", "audit_log",            # platform
    "webhooks", "settings",
}


# ── UUID v7 ───────────────────────────────────────────────────────────────────
def test_uuid7_is_version_7_variant_10():
    u = uuid7()
    assert (u.int >> 76) & 0xF == 0x7          # version nibble
    assert (u.int >> 62) & 0x3 == 0b10         # RFC 4122 variant
    assert u.version == 7


def test_uuid7_is_time_ordered_and_unique():
    xs = [uuid7() for _ in range(2000)]
    assert len(set(xs)) == 2000                 # no collisions
    assert xs == sorted(xs)                      # minted in ascending order


# ── schema shape ──────────────────────────────────────────────────────────────
def test_all_srs_section_8_tables_present():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_mutable_tables_carry_the_audit_quartet():
    for t in ("applications", "data_sources", "scan_jobs", "findings", "dpia_assessments"):
        cols = set(Base.metadata.tables[t].columns.keys())
        assert {"created_at", "updated_at", "created_by", "updated_by"} <= cols, t


def test_every_primary_key_is_uuid_or_natural():
    for name, table in Base.metadata.tables.items():
        assert table.primary_key.columns, f"{name} has no primary key"


def test_findings_is_list_partitioned_with_composite_key():
    f = Base.metadata.tables["findings"]
    assert f.dialect_options["postgresql"]["partition_by"] == "LIST (scan_job_id)"
    assert {c.name for c in f.primary_key.columns} == {"id", "scan_job_id"}


def test_applications_tags_has_a_gin_index():
    gin = [i for i in Base.metadata.tables["applications"].indexes
           if i.dialect_options["postgresql"].get("using") == "gin"]
    assert any("tags" in i.name for i in gin)


def test_whole_schema_compiles_for_postgres():
    for name, table in Base.metadata.tables.items():
        str(CreateTable(table).compile(dialect=PG))   # raises on any bad type/arg


# ── enums ─────────────────────────────────────────────────────────────────────
def test_detection_enums_are_the_core_ones():
    # The DB must not define its own Tier/ReviewState — it reuses dpia_core's so a
    # finding written by the engine maps to the same labels.
    assert enums.Tier is core.Tier
    assert enums.ReviewState is core.ReviewState
    assert enums.Category is core.Category


def test_pg_enum_labels_are_values_not_names():
    # values_callable must make the PG ENUM labels the lowercase .value strings.
    assert set(enums.role_enum.enums) == {"admin", "dpo", "owner", "auditor", "operator"}
    assert "very_high" in enums.risk_band_enum.enums
    assert "under_review" in enums.dpia_state_enum.enums


# ── RLS + audit DDL contract (SRS 8.4 / 8.5) ──────────────────────────────────
def test_rls_covers_exactly_the_scoped_tables():
    assert set(ddl.RLS_TABLES) == {
        "applications", "data_sources", "findings", "inventory",
        "dpia_assessments", "questionnaire_responses", "dpia_comments",
        "risks", "dpia_transitions", "dpia_records", "change_events",
    }
    # applications is keyed on its own id; the rest on application_id.
    assert ddl.RLS_TABLES["applications"] == "id"
    assert ddl.RLS_TABLES["findings"] == "application_id"


def test_rls_up_forces_rls_and_installs_a_bypass_aware_policy():
    sql = "\n".join(ddl.rls_up())
    assert sql.count("FORCE ROW LEVEL SECURITY") == len(ddl.RLS_TABLES)
    assert sql.count("CREATE POLICY") == len(ddl.RLS_TABLES)
    assert ddl.SESSION_VAR_BYPASS in sql and ddl.SESSION_VAR_APP_IDS in sql
    assert "WITH CHECK" in sql                  # writes are constrained too


def test_audit_trigger_is_append_only():
    up = "\n".join(ddl.audit_trigger_up())
    assert "BEFORE UPDATE OR DELETE ON audit_log" in up
    assert "RAISE EXCEPTION" in up
    down = "\n".join(ddl.audit_trigger_down())
    assert "DROP TRIGGER" in down and "DROP FUNCTION" in down


# ── session / RLS context setter ──────────────────────────────────────────────
def test_normalise_async_url_targets_psycopg():
    assert normalise_async_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    # already-qualified URLs are left alone
    assert normalise_async_url("postgresql+psycopg://x/db") == "postgresql+psycopg://x/db"


def test_set_rls_context_sets_both_locals():
    calls: list[tuple[str, str]] = []

    class _FakeSession:
        async def execute(self, _stmt, params):
            calls.append((params["k"], params["v"]))

    app_ids = [uuid.uuid4(), uuid.uuid4()]
    asyncio.run(set_rls_context(_FakeSession(), app_ids, bypass=False))
    recorded = dict(calls)
    assert recorded[ddl.SESSION_VAR_APP_IDS] == ",".join(str(a) for a in app_ids)
    assert recorded[ddl.SESSION_VAR_BYPASS] == "off"

    calls.clear()
    asyncio.run(set_rls_context(_FakeSession(), None, bypass=True))
    recorded = dict(calls)
    assert recorded[ddl.SESSION_VAR_APP_IDS] == ""      # no apps -> empty -> fail closed
    assert recorded[ddl.SESSION_VAR_BYPASS] == "on"


# ── migration module ──────────────────────────────────────────────────────────
def test_baseline_migration_is_the_root_revision():
    # The module name starts with a digit, so load it by path rather than import.
    mod = _load_baseline()
    assert mod.revision == "0001"
    assert mod.down_revision is None
    assert callable(mod.upgrade) and callable(mod.downgrade)


def _load_baseline():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "platform_db" / "migrations" / \
        "versions" / "0001_baseline.py"
    spec = importlib.util.spec_from_file_location("baseline_0001", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
