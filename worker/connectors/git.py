"""Git connector (SRS FR-2.1 / FR-2.2).

Walks a repository working tree, skips VCS/build/vendored noise and binaries, and
scans each source file two ways:

  * **values** — every line is run through ``evaluate_text`` so a hard-coded Aadhaar,
    PAN, email or phone number in a string literal, comment or sample row is caught
    with a file:line locator;
  * **identifiers** — each distinct identifier (field/column/variable/parameter name)
    is run through the engine's schema-only path, so a column named ``aadhaar`` or a
    DTO field ``panNumber`` is caught even when no literal value appears. Name-only
    detection fires only on an exact keyword match, so scanning every token is safe
    (a keyword like ``class`` or ``return`` matches no PII detector).

Findings for one file share a unit, so co-occurrence raises combined-identity records
per file (SRS 4.3). Cloning/pulling (FR-2.1) is an injected step — this environment
has no GitPython, and a connector that scans an existing checkout needs none — so the
scanning core is exercised without any VCS dependency.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Iterable

from dpia_core.detectors.registry import DEFAULT_PACK_VERSION, default_detectors
from dpia_core.engine import apply_cooccurrence, evaluate_column, evaluate_text
from dpia_core.models import Finding, Locator, ScanProfile
from worker.connectors.base import ConnectorTest, ScanUnit
from worker.connectors.ignore import IgnoreRules

# Source file families the connector parses (FR-2.2): Python, Java, C#,
# JavaScript/TypeScript, SQL and PL/SQL.
SOURCE_EXTENSIONS = frozenset({
    ".py", ".java", ".cs", ".js", ".jsx", ".ts", ".tsx",
    ".sql", ".ddl", ".pks", ".pkb", ".pls",
})

# Identifiers of length >= 2 (a single letter is never a PII keyword and adds noise).
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")

_DEFAULT_MAX_FILE_BYTES = 2_000_000


class GitConnector:
    """Scan a repository working tree into findings (implements the SDK contract)."""

    def __init__(
        self,
        root: str,
        *,
        detectors=None,
        pack_version: str = DEFAULT_PACK_VERSION,
        ignore: IgnoreRules | None = None,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
        cloner: Callable[..., str] | None = None,
        profile: ScanProfile = ScanProfile.STANDARD,
    ):
        self.root = os.path.abspath(root)
        self.detectors = detectors if detectors is not None else default_detectors()
        self.pack_version = pack_version
        self.ignore = ignore if ignore is not None else IgnoreRules.from_root(self.root)
        self.max_file_bytes = max_file_bytes
        self._cloner = cloner
        self.profile = profile

    # ── SDK contract ─────────────────────────────────────────────────────────
    def test(self) -> ConnectorTest:
        if not os.path.isdir(self.root):
            return ConnectorTest(ok=False, detail=f"not a directory: {self.root}")
        return ConnectorTest(ok=True, detail=f"readable working tree at {self.root}")

    def enumerate(self) -> Iterable[ScanUnit]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune ignored directories in place so os.walk never descends into them.
            dirnames[:] = [d for d in dirnames if not self.ignore.dir_ignored(d)]
            for fn in filenames:
                abspath = os.path.join(dirpath, fn)
                rel = os.path.relpath(abspath, self.root).replace(os.sep, "/")
                if os.path.splitext(fn)[1].lower() not in SOURCE_EXTENSIONS:
                    continue
                if self.ignore.file_ignored(rel):
                    continue
                yield ScanUnit(kind="file", key=rel, meta={"abs": abspath})

    def scan_unit(self, unit: ScanUnit) -> list[Finding]:
        abspath = unit.meta.get("abs") or os.path.join(self.root, unit.key)
        text = self._read(abspath)
        if text is None:
            return []
        findings = self._scan_values(unit.key, text) + self._scan_identifiers(unit.key, text)
        return apply_cooccurrence(findings)

    def fingerprint(self, unit: ScanUnit) -> str | None:
        """A cheap change marker (size + mtime) for incremental scans; None if unknown."""
        abspath = unit.meta.get("abs") or os.path.join(self.root, unit.key)
        try:
            st = os.stat(abspath)
        except OSError:
            return None
        return f"{st.st_size}:{int(st.st_mtime)}"

    # ── convenience ──────────────────────────────────────────────────────────
    def scan_all(self) -> list[Finding]:
        out: list[Finding] = []
        for unit in self.enumerate():
            out.extend(self.scan_unit(unit))
        return out

    def clone_or_pull(self, url: str, dest: str | None = None, **kwargs) -> str:
        """Clone or pull ``url`` using the injected ``cloner`` and point the connector
        at the result. Cloning needs a VCS client (GitPython or a git subprocess),
        which is supplied by the caller — the scan core itself requires none."""
        if self._cloner is None:
            raise RuntimeError(
                "no git cloner configured; scan an existing checkout, or pass "
                "cloner=... (GitPython is not installed in this environment)")
        path = self._cloner(url, dest, **kwargs)
        self.root = os.path.abspath(path)
        self.ignore = IgnoreRules.from_root(self.root)
        return self.root

    # ── internals ──────────────────────────────────────────────────────────────
    def _read(self, abspath: str) -> str | None:
        try:
            if os.path.getsize(abspath) > self.max_file_bytes:
                return None
            with open(abspath, "rb") as fh:
                raw = fh.read()
        except OSError:
            return None
        if b"\x00" in raw[:8192]:            # a NUL byte early => treat as binary, skip
            return None
        return raw.decode("utf-8", errors="replace")

    def _scan_values(self, rel_path: str, text: str) -> list[Finding]:
        """Value detection, line by line, so every hit carries a precise line."""
        findings: list[Finding] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            findings.extend(evaluate_text(
                self.detectors, line, path=rel_path, line=lineno,
                pack_version=self.pack_version, profile=self.profile))
        return findings

    def _scan_identifiers(self, rel_path: str, text: str) -> list[Finding]:
        """Name detection: each distinct identifier via the engine's schema-only path,
        then relocate the DB-style locator the engine produces onto this file:line."""
        first_line: dict[str, int] = {}
        for lineno, line in enumerate(text.splitlines(), start=1):
            for tok in _IDENTIFIER_RE.findall(line):
                if tok not in first_line:
                    first_line[tok] = lineno
        findings: list[Finding] = []
        for tok, lineno in first_line.items():
            named = evaluate_column(
                self.detectors, tok, [], profile=ScanProfile.QUICK,
                pack_version=self.pack_version)
            for f in named:
                # The engine locates a column finding in the database plane; re-address
                # it to the source file where the identifier appears.
                f.locator = Locator(kind="file", path=rel_path, line=lineno)
            findings.extend(named)
        return findings
