"""PostgreSQL connector — detection logic without a database (SRS FR-2.3 / FR-2.4).

The I/O (connect, enumerate, sample) is covered by the live integration test; here we
test the pure ``_rows_to_findings`` mapping and the safety defaults, which need no DB.
"""
from __future__ import annotations

from dpia_core.models import Category, ScanProfile
from worker.connectors.postgres import SYSTEM_SCHEMAS, PostgresConnector

COLUMNS = [
    {"name": "full_name", "data_type": "text", "comment": None},
    {"name": "email", "data_type": "text", "comment": None},
    {"name": "pan_no", "data_type": "char", "comment": None},
]
ROWS = [
    ("Ananya Roy", "ananya.roy@example.com", "ABCPK1234L"),
    ("Rahul Verma", "rahul.verma@example.com", "AAAPL1234C"),
]


def _connector(profile=ScanProfile.STANDARD):
    # connect is never called by _rows_to_findings, so a stub is fine here.
    return PostgresConnector("postgresql://unused", profile=profile,
                             connect=lambda dsn: None)


def test_values_are_detected_with_database_locators():
    findings = _connector()._rows_to_findings("public", "customers", COLUMNS, ROWS)
    cats = {f.category for f in findings}
    assert Category.EMAIL in cats and Category.PAN in cats
    for f in findings:
        assert f.locator.kind == "database"
        assert f.locator.schema == "public" and f.locator.table == "customers"
        assert f.locator.column in {"full_name", "email", "pan_no"}


def test_value_hits_carry_hit_rate_and_plain_protection():
    findings = _connector()._rows_to_findings("public", "customers", COLUMNS, ROWS)
    email = next(f for f in findings if f.category == Category.EMAIL)
    assert email.hit_rate == 1.0 and email.confidence >= 0.80


def test_quick_profile_detects_from_the_column_name_without_values():
    # Schema-only: no rows, but a column named like a category still flags (name context).
    cols = [{"name": "aadhaar_number", "data_type": "char", "comment": None}]
    findings = _connector(ScanProfile.QUICK)._rows_to_findings("app", "kyc", cols, [])
    assert any(f.category == Category.AADHAAR and f.hit_rate == 0.0 for f in findings)


def test_cooccurrence_flags_a_combined_identity_table():
    findings = _connector()._rows_to_findings("public", "customers", COLUMNS, ROWS)
    assert findings and all(f.combined_identity for f in findings)


def test_system_schemas_are_excluded_by_default():
    assert {"pg_catalog", "information_schema", "pg_toast"} <= SYSTEM_SCHEMAS
    assert _connector().schemas_exclude == SYSTEM_SCHEMAS


def test_deep_profile_raises_the_sample_cap():
    assert _connector(ScanProfile.DEEP).sample_cap >= 1000
    assert _connector(ScanProfile.STANDARD).sample_cap < 1000
