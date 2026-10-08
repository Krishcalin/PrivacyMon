"""Deeper discovery: NER soft-import, custom-detector compilation, and the OpenAPI /
filesystem connectors (SRS 4.1 / FR-2.3 / FR-4.7). DB-free; the live custom-detector and
incremental flows are exercised by the Docker validation.
"""
from __future__ import annotations

import json

import pytest

from dpia_core import ner
from dpia_core.detectors.compile import (
    DetectorCompileError, VALIDATOR_REGISTRY, spec_from_row, validator_names,
)
from dpia_core.models import Category, DetectorKind, Tier


# ── NER soft-import ───────────────────────────────────────────────────────────
def test_ner_degrades_without_spacy():
    # In this environment spaCy is not installed; every entry point must be safe.
    assert ner.extract_entities("Rajesh Kumar lives at 12 MG Road, Mumbai 400001") == []
    assert isinstance(ner.ner_available(), bool)


def test_ner_empty_text():
    assert ner.extract_entities("") == []
    assert ner.extract_entities("   ") == []


# ── custom-detector compilation ───────────────────────────────────────────────
def test_compile_pattern_validator():
    spec = spec_from_row({"id": "x", "category": "pan", "tier": "high",
                          "pattern": r"[A-Z]{5}\d{4}[A-Z]", "validator": "pan_valid"})
    assert spec.kind == DetectorKind.PATTERN_VALIDATOR
    assert spec.category == Category.PAN and spec.tier == Tier.HIGH
    assert spec.id == "custom.x"
    assert spec.pattern is not None and spec.validator is VALIDATOR_REGISTRY["pan_valid"]


def test_compile_pattern_only():
    spec = spec_from_row({"id": "emp", "category": "email", "tier": "medium",
                          "pattern": r"EMP\d{6}"})
    assert spec.kind == DetectorKind.PATTERN
    assert spec.validator is None


def test_compile_dictionary_requires_context():
    with pytest.raises(DetectorCompileError, match="context_positive"):
        spec_from_row({"id": "d", "category": "health", "tier": "high"})
    spec = spec_from_row({"id": "d", "category": "health", "tier": "high",
                          "context_positive": ["diagnosis", "icd"]})
    assert spec.kind == DetectorKind.DICTIONARY
    assert spec.requires_context is True


def test_compile_rejects_bad_regex():
    with pytest.raises(DetectorCompileError, match="invalid regex"):
        spec_from_row({"id": "b", "category": "pan", "tier": "high", "pattern": "([a-z"})


def test_compile_rejects_unknown_validator():
    with pytest.raises(DetectorCompileError, match="unknown validator"):
        spec_from_row({"id": "b", "category": "pan", "tier": "high",
                       "validator": "os.system"})


def test_validator_registry_is_names_only():
    names = validator_names()
    assert "pan_valid" in names and "aadhaar_valid" in names
    # No dunder / attribute escape hatch — only the vetted names.
    assert all("." not in n and not n.startswith("__") for n in names)


def test_compiled_custom_detector_fires_in_engine():
    from dpia_core.engine import evaluate_column
    spec = spec_from_row({"id": "emp", "category": "email", "tier": "medium",
                          "pattern": r"EMP\d{6}", "context_positive": ["employee"]})
    findings = evaluate_column([spec], "employee_code", ["EMP123456", "EMP999000"])
    assert findings and findings[0].category == Category.EMAIL
    assert findings[0].detector_id == "custom.emp"


# ── OpenAPI connector ─────────────────────────────────────────────────────────
def _spec_file(tmp_path):
    spec = {
        "openapi": "3.0.0",
        "components": {"schemas": {
            "Customer": {"properties": {
                "pan": {"type": "string", "example": "ABCPD1234F"},
                "email_address": {"type": "string"},
                "full_name": {"type": "string"},
            }},
        }},
    }
    p = tmp_path / "api.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return str(p)


def test_openapi_connector_finds_schema_pii(tmp_path):
    from worker.connectors.openapi import OpenApiConnector
    c = OpenApiConnector(_spec_file(tmp_path))
    assert c.test().ok
    units = list(c.enumerate())
    assert len(units) == 1 and units[0].key == "schema:Customer"
    findings = c.scan_unit(units[0])
    cats = {f.category for f in findings}
    assert Category.PAN in cats          # value example ABCPD1234F
    assert Category.EMAIL in cats        # field name email_address
    # locator addresses the API schema plane
    assert any(f.locator.table == "Customer" for f in findings)


def test_openapi_presence_only_drops_values(tmp_path):
    from worker.connectors.openapi import OpenApiConnector
    c = OpenApiConnector(_spec_file(tmp_path), presence_only=True)
    findings = c.scan_unit(next(iter(c.enumerate())))
    assert findings and all(f.evidence == [] for f in findings)


# ── filesystem connector ──────────────────────────────────────────────────────
def test_filesystem_connector_scans_csv(tmp_path):
    from worker.connectors.filesystem import FilesystemConnector
    (tmp_path / "export.csv").write_text(
        "name,pan,email\nAsha,ABCPD1234F,asha@example.com\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("contact asha@example.com for KYC\n", encoding="utf-8")
    c = FilesystemConnector(str(tmp_path))
    assert c.test().ok
    keys = {u.key for u in c.enumerate()}
    assert "export.csv" in keys and "notes.txt" in keys
    all_findings = c.scan_all()
    cats = {f.category.value for f in all_findings}
    # pan from the CSV header name + valid value; email from the header, the CSV value
    # and the free-text .txt. (A bare phone number in free text needs column context to
    # fire, by design, so it is deliberately not asserted here.)
    assert "pan" in cats and "email" in cats


def test_filesystem_fingerprint_changes_with_content(tmp_path):
    from worker.connectors.base import ScanUnit
    from worker.connectors.filesystem import FilesystemConnector
    f = tmp_path / "a.csv"
    f.write_text("pan\nABCPD1234F\n", encoding="utf-8")
    c = FilesystemConnector(str(tmp_path))
    unit = ScanUnit(kind="file", key="a.csv", meta={"abs": str(f)})
    fp1 = c.fingerprint(unit)
    assert fp1 is not None
    f.write_text("pan\nABCPD1234F\nZZZZZ9999Z\n", encoding="utf-8")
    assert c.fingerprint(unit) != fp1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
