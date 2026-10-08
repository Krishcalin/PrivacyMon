"""Filesystem / file-share connector (SRS FR-2.3): scan documents on a mounted path —
a network share (SMB/NFS) mounted into the worker, an export directory, a data drop.

Where the Git connector targets source code, this targets DATA files: CSV, TSV, JSON,
NDJSON, text, logs, YAML, markdown. Each file is a scan unit; its text is scanned with
``evaluate_text`` (value detection, line by line) so a leaked Aadhaar, PAN, email or
phone number in a spreadsheet export or log is caught with a file:line locator. For
tabular files the header row additionally drives schema-only name detection (a column
named ``pan`` or ``aadhaar``). On the Deep profile, NER surfaces free-text names and
addresses. Binary and oversized files are skipped. Presence-only drops every value
fragment, recording only which categories a file holds.
"""
from __future__ import annotations

import csv
import io
import os
from typing import Iterable

from dpia_core.detectors.registry import DEFAULT_PACK_VERSION, default_detectors
from dpia_core.engine import apply_cooccurrence, evaluate_column, evaluate_text
from dpia_core.models import Finding, Locator, ScanProfile
from worker.connectors.base import ConnectorTest, ScanUnit
from worker.connectors.ignore import IgnoreRules

# Data-file families this connector reads (distinct from source code).
DATA_EXTENSIONS = frozenset({
    ".csv", ".tsv", ".txt", ".log", ".json", ".ndjson", ".jsonl",
    ".yaml", ".yml", ".md", ".tab", ".dat",
})
_TABULAR = frozenset({".csv", ".tsv", ".tab"})
_DEFAULT_MAX_FILE_BYTES = 10_000_000
_MAX_LINES = 50_000           # cap work per file; a share can hold huge exports


class FilesystemConnector:
    """Scan a directory tree of data files into findings (implements the SDK contract)."""

    def __init__(
        self,
        root: str,
        *,
        detectors=None,
        pack_version: str = DEFAULT_PACK_VERSION,
        ignore: IgnoreRules | None = None,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
        profile: ScanProfile = ScanProfile.STANDARD,
        presence_only: bool = False,
        extensions: frozenset[str] = DATA_EXTENSIONS,
    ):
        self.root = os.path.abspath(root)
        self.detectors = detectors if detectors is not None else default_detectors()
        self.pack_version = pack_version
        self.ignore = ignore if ignore is not None else IgnoreRules.from_root(self.root)
        self.max_file_bytes = max_file_bytes
        self.profile = profile
        self.presence_only = presence_only
        self.extensions = extensions

    # ── SDK contract ─────────────────────────────────────────────────────────
    def test(self) -> ConnectorTest:
        if not os.path.isdir(self.root):
            return ConnectorTest(ok=False, detail=f"not a directory: {self.root}")
        if not os.access(self.root, os.R_OK):
            return ConnectorTest(ok=False, detail=f"not readable: {self.root}")
        return ConnectorTest(ok=True, detail=f"readable file share at {self.root}")

    def enumerate(self) -> Iterable[ScanUnit]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not self.ignore.dir_ignored(d)]
            for fn in filenames:
                abspath = os.path.join(dirpath, fn)
                rel = os.path.relpath(abspath, self.root).replace(os.sep, "/")
                if os.path.splitext(fn)[1].lower() not in self.extensions:
                    continue
                if self.ignore.file_ignored(rel):
                    continue
                yield ScanUnit(kind="file", key=rel, meta={"abs": abspath})

    def scan_unit(self, unit: ScanUnit) -> list[Finding]:
        abspath = unit.meta.get("abs") or os.path.join(self.root, unit.key)
        text = self._read(abspath)
        if text is None:
            return []
        ext = os.path.splitext(unit.key)[1].lower()
        findings = self._scan_values(unit.key, text)
        if ext in _TABULAR:
            findings += self._scan_header(unit.key, text, delimiter="\t" if ext == ".tsv" else ",")
        if self.presence_only:
            for f in findings:
                f.evidence = []
        return apply_cooccurrence(findings)

    def scan_all(self) -> list[Finding]:
        out: list[Finding] = []
        for unit in self.enumerate():
            out.extend(self.scan_unit(unit))
        return out

    def fingerprint(self, unit: ScanUnit) -> str | None:
        """A cheap change marker (size + mtime) for incremental scans; None if unknown."""
        abspath = unit.meta.get("abs") or os.path.join(self.root, unit.key)
        try:
            st = os.stat(abspath)
        except OSError:
            return None
        return f"{st.st_size}:{int(st.st_mtime)}"

    # ── internals ──────────────────────────────────────────────────────────────
    def _read(self, abspath: str) -> str | None:
        try:
            if os.path.getsize(abspath) > self.max_file_bytes:
                return None
            with open(abspath, "rb") as fh:
                raw = fh.read()
        except OSError:
            return None
        if b"\x00" in raw[:8192]:
            return None
        return raw.decode("utf-8", errors="replace")

    def _scan_values(self, rel_path: str, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if lineno > _MAX_LINES:
                break
            if not line.strip():
                continue
            findings.extend(evaluate_text(
                self.detectors, line, path=rel_path, line=lineno,
                pack_version=self.pack_version, profile=self.profile))
        return findings

    def _scan_header(self, rel_path: str, text: str, *, delimiter: str) -> list[Finding]:
        """Treat a tabular file's header row as column names (schema-only detection)."""
        try:
            first = text.splitlines()[0] if text.splitlines() else ""
            header = next(csv.reader(io.StringIO(first), delimiter=delimiter), [])
        except Exception:  # noqa: BLE001
            return []
        findings: list[Finding] = []
        for col in header:
            col = col.strip()
            if not col:
                continue
            named = evaluate_column(self.detectors, col, [], profile=ScanProfile.QUICK,
                                    pack_version=self.pack_version)
            for f in named:
                f.locator = Locator(kind="file", path=rel_path, line=1)
            findings.extend(named)
        return findings
