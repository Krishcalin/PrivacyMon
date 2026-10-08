"""The connector SDK contract (SRS FR-2.9).

A connector enumerates the units it will scan (files for Git, columns/tables for a
database) and scans each unit into ``dpia_core`` findings. ``test()`` validates
reachability before a data source is saved (FR-2.6). Keeping this as a ``Protocol``
means the pipeline depends on the shape, not on any one connector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

from dpia_core.models import Finding


@dataclass(frozen=True)
class ConnectorTest:
    """Result of a connectivity check (FR-2.6)."""

    ok: bool
    detail: str = ""


@dataclass
class ScanUnit:
    """One addressable thing to scan — a file (Git) or a table/column (database).

    ``key`` is a stable identifier for progress and resumability (SRS 8.2
    ``scan_units.locator``); ``meta`` carries connector-specific addressing (absolute
    path, schema/table, …) without the pipeline needing to understand it.
    """

    kind: str                       # "file" | "table" | "column"
    key: str                        # repo-relative path, or schema.table[.column]
    meta: dict = field(default_factory=dict)


@runtime_checkable
class Connector(Protocol):
    """Every connector implements these three (FR-2.9)."""

    def test(self) -> ConnectorTest:
        """Validate credentials and reachability without scanning."""
        ...

    def enumerate(self) -> Iterable[ScanUnit]:
        """List the units to scan, after ignore/selection rules."""
        ...

    def scan_unit(self, unit: ScanUnit) -> list[Finding]:
        """Sample the unit and run detectors, returning findings for it."""
        ...
