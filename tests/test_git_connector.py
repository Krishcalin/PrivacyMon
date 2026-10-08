"""Tests for the Git connector (SRS FR-2.1 / FR-2.2).

Scans the committed ``fixtures/repo`` working tree (no VCS clone needed) and a few
synthetic trees for the ignore rules. Detector precision is the engine's concern
(tested elsewhere at 1.00); here we assert the CONNECTOR: enumeration, ignore rules,
file:line locators, value- and name-based detection, and per-file co-occurrence.
"""
from __future__ import annotations

import os

from dpia_core.models import Category
from worker.connectors.git import GitConnector
from worker.connectors.ignore import IgnoreRules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "fixtures", "repo")


# ── enumeration + test() ──────────────────────────────────────────────────────
def test_test_ok_on_a_directory_and_not_on_a_missing_path():
    assert GitConnector(FIXTURE).test().ok is True
    bad = GitConnector(os.path.join(FIXTURE, "does-not-exist"))
    assert bad.test().ok is False


def test_enumerate_returns_the_source_files():
    keys = {u.key for u in GitConnector(FIXTURE).enumerate()}
    assert keys == {"src/customer_model.py", "src/schema.sql"}


# ── scanning the fixture ────────────────────────────────────────────────────────
def test_scan_finds_the_expected_categories_with_file_locators():
    findings = GitConnector(FIXTURE).scan_all()
    assert findings, "the connector found nothing in the fixture"
    cats = {f.category for f in findings}
    for expected in (Category.AADHAAR, Category.PAN, Category.EMAIL,
                     Category.BIOMETRIC, Category.PERSON_NAME):
        assert expected in cats, expected
    for f in findings:
        assert f.locator.kind == "file"
        assert f.locator.path in ("src/customer_model.py", "src/schema.sql")
        assert isinstance(f.locator.line, int) and f.locator.line >= 1


def test_value_detection_catches_a_hardcoded_literal():
    # customer_model.py embeds "ananya.roy@example.com" — a value hit is high confidence
    # (pattern+validator), unlike the name-only signal from an `email` identifier.
    findings = GitConnector(FIXTURE).scan_all()
    email_values = [f for f in findings
                    if f.category == Category.EMAIL and f.hit_rate == 1.0
                    and f.confidence >= 0.80]
    assert email_values, "no high-confidence email VALUE finding from the literal"
    assert any(f.locator.path == "src/customer_model.py" for f in email_values)


def test_name_detection_catches_an_identifier_without_a_value():
    # The `aadhaar_number` field/column name is a signal even where no value appears.
    findings = GitConnector(FIXTURE).scan_all()
    name_only = [f for f in findings
                 if f.category == Category.AADHAAR and f.hit_rate == 0.0]
    assert name_only, "no name-based Aadhaar finding from the identifier"


def test_cooccurrence_flags_combined_identity_per_file():
    findings = GitConnector(FIXTURE).scan_all()
    model = [f for f in findings if f.locator.path == "src/customer_model.py"]
    assert model and all(f.combined_identity for f in model), \
        "a file holding several categories must raise combined-identity records"


# ── ignore rules ──────────────────────────────────────────────────────────────
def test_ignore_skips_build_and_vendor_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("z = 3\n", encoding="utf-8")
    keys = {u.key for u in GitConnector(str(tmp_path)).enumerate()}
    assert keys == {"src/app.py"}


def test_ignore_skips_non_source_and_binary(tmp_path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")   # not source
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\x00\x00")            # binary ext
    keys = {u.key for u in GitConnector(str(tmp_path)).enumerate()}
    assert keys == {"a.py"}


def test_gitignore_patterns_are_honoured(tmp_path):
    (tmp_path / ".gitignore").write_text("secrets.py\n*.generated.sql\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "secrets.py").write_text("KEY='x'\n", encoding="utf-8")
    (tmp_path / "schema.generated.sql").write_text("CREATE TABLE t();\n", encoding="utf-8")
    keys = {u.key for u in GitConnector(str(tmp_path)).enumerate()}
    assert keys == {"app.py"}


def test_binary_file_with_source_extension_is_skipped(tmp_path):
    (tmp_path / "blob.sql").write_bytes(b"CREATE\x00\x00TABLE binary junk")
    findings = GitConnector(str(tmp_path)).scan_all()
    assert findings == []


def test_clone_without_a_cloner_is_a_clear_error(tmp_path):
    import pytest
    c = GitConnector(str(tmp_path))
    with pytest.raises(RuntimeError, match="no git cloner"):
        c.clone_or_pull("https://example.com/repo.git")


# ── ignore unit ─────────────────────────────────────────────────────────────────
def test_ignore_rules_unit():
    r = IgnoreRules(gitignore_patterns=["build/", "*.min.js", "/root_only.py"])
    assert r.dir_ignored("node_modules") and r.dir_ignored(".git")
    assert r.file_ignored("app.min.js")
    assert r.file_ignored("pkg/logo.png")          # binary extension
    assert r.file_ignored("build/x.py")            # inside an ignored dir name
    assert r.file_ignored("root_only.py")          # root-anchored pattern
    assert not r.file_ignored("src/app.py")
