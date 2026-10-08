"""Findings-review & suppression logic — the pure, DB-free parts (SRS FR-4.6).

These cover the pipeline's cross-scan suppression matching and the audit writer's
JSON coercion. Live review/suppress/inventory-edit endpoints are exercised by the
Docker validation (and would need a running database).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from api.app import audit
from api.app.console import _matches, _suppression_match
from dpia_core.models import Category
from worker.pipeline import _suppressed_by


# ── suppression key (console helper) ──────────────────────────────────────────
def test_suppression_match_column_scope_keeps_full_locator():
    loc = {"kind": "column", "schema": "public", "table": "users", "column": "pan", "line": None}
    key = _suppression_match(loc, "column")
    assert key == {"schema": "public", "table": "users", "column": "pan"}


def test_suppression_match_table_scope_drops_column():
    loc = {"schema": "public", "table": "users", "column": "pan"}
    assert _suppression_match(loc, "table") == {"schema": "public", "table": "users"}


def test_suppression_match_path_scope_for_files():
    loc = {"kind": "file", "path": "src/app.py", "line": 42}
    assert _suppression_match(loc, "path") == {"path": "src/app.py"}


def test_suppression_match_table_scope_on_file_uses_path_not_empty():
    # A file finding has no schema/table — "table" scope must fall back to the path,
    # never to an empty match (which would suppress every finding of that category).
    loc = {"kind": "file", "path": "src/app.py", "line": 42, "table": None, "schema": None}
    assert _suppression_match(loc, "table") == {"path": "src/app.py"}


def test_suppression_match_never_empty():
    # Even a sparse locator yields a non-empty key so a suppression can't match all.
    assert _suppression_match({"column": "pan"}, "table") == {"column": "pan"}


def test_matches_is_subset_containment():
    loc = {"schema": "public", "table": "users", "column": "pan"}
    assert _matches(loc, {"table": "users", "column": "pan"})
    assert not _matches(loc, {"table": "orders"})
    assert _matches(loc, {})          # empty match = matches everything


# ── cross-scan suppression (pipeline helper) ──────────────────────────────────
def _sup(**kw):
    kw.setdefault("category", None)
    return SimpleNamespace(id=uuid.uuid4(), **kw)


def test_suppressed_by_matches_locator_and_category():
    loc = {"schema": "public", "table": "users", "column": "pan"}
    s = _sup(locator_match={"table": "users", "column": "pan"}, category=Category.PAN)
    assert _suppressed_by(loc, Category.PAN, [s]) is s


def test_suppressed_by_rejects_other_category():
    loc = {"table": "users", "column": "pan"}
    s = _sup(locator_match={"table": "users", "column": "pan"}, category=Category.PAN)
    assert _suppressed_by(loc, Category.EMAIL, [s]) is None


def test_suppressed_by_category_none_matches_any():
    loc = {"table": "users", "column": "pan"}
    s = _sup(locator_match={"table": "users"}, category=None)
    assert _suppressed_by(loc, Category.PAN, [s]) is s
    assert _suppressed_by(loc, Category.EMAIL, [s]) is s


def test_suppressed_by_table_scope_covers_every_column():
    s = _sup(locator_match={"schema": "public", "table": "users"})
    assert _suppressed_by({"schema": "public", "table": "users", "column": "pan"},
                          Category.PAN, [s]) is s
    assert _suppressed_by({"schema": "public", "table": "users", "column": "email"},
                          Category.EMAIL, [s]) is s
    assert _suppressed_by({"schema": "public", "table": "orders", "column": "pan"},
                          Category.PAN, [s]) is None


def test_suppressed_by_returns_none_when_no_suppressions():
    assert _suppressed_by({"table": "users"}, Category.PAN, []) is None


# ── audit JSON coercion (DB-free) ─────────────────────────────────────────────
def test_audit_jsonable_coerces_uuid_and_nested():
    u = uuid.uuid4()
    out = audit._jsonable({"id": u, "nums": [1, 2], "flag": True, "none": None})
    assert out == {"id": str(u), "nums": [1, 2], "flag": True, "none": None}


def test_audit_record_never_raises_on_bad_session():
    # A broken session must not propagate — auditing is best-effort.
    class Bad:
        def add(self, *_):
            raise RuntimeError("boom")

    audit.record(Bad(), actor_id=None, action="x.y", object_type="t")  # no exception


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
