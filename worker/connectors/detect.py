"""Shared column-detection logic, used by every database connector so a scan behaves
identically whatever the engine (PostgreSQL, MySQL, Oracle, SQL Server).

Given a table's sampled rows and column metadata, run ``evaluate_column`` per column and
fold co-occurrence. In presence-only mode no value — not even a masked fragment — is
kept: the sampled values are read transiently to recognise the pattern, then discarded;
only the column, category and presence metrics remain.
"""
from __future__ import annotations

from dpia_core.engine import apply_cooccurrence, evaluate_column
from dpia_core.models import Finding, ScanProfile


def scan_columns(
    detectors,
    schema: str,
    table: str,
    columns: list[dict],
    rows: list[tuple],
    *,
    profile: ScanProfile,
    pack_version: str,
    presence_only: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    for idx, col in enumerate(columns):
        values = [r[idx] for r in rows] if rows else []
        findings.extend(evaluate_column(
            detectors, col["name"], values, data_type=col.get("data_type"),
            schema=schema, table=table, profile=profile, pack_version=pack_version))
    if presence_only:
        for f in findings:
            f.evidence = []                  # record the presence, never a value fragment
    return apply_cooccurrence(findings)
