"""OpenAPI / Swagger connector (SRS FR-2.3): discover personal data in an API contract.

An API often exposes PII through its request/response schemas before any database is
reached. This connector reads an OpenAPI 3.x (or Swagger 2.0) document — from a URL or a
local path, JSON or YAML — and walks ``components.schemas`` (and 2.0 ``definitions``).
Each schema is a scan unit; each property is treated as a column:
  * the property NAME drives schema-only detection (a field ``aadhaar`` / ``panNumber``);
  * any ``example`` / ``default`` / ``enum`` VALUES are scanned for literal PII.
Presence-only drops value fragments. No endpoint is ever called — only the contract is
read — so this is safe against a production API's documentation.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Iterable

from dpia_core.detectors.registry import DEFAULT_PACK_VERSION, default_detectors
from dpia_core.engine import apply_cooccurrence, evaluate_column
from dpia_core.models import Finding, Locator, ScanProfile
from worker.connectors.base import ConnectorTest, ScanUnit


class OpenApiConnector:
    """Scan an OpenAPI/Swagger document's schemas into findings (SDK contract)."""

    def __init__(
        self,
        source: str,
        *,
        detectors=None,
        pack_version: str = DEFAULT_PACK_VERSION,
        profile: ScanProfile = ScanProfile.STANDARD,
        presence_only: bool = False,
        timeout: float = 10.0,
    ):
        self.source = source                 # URL or local path to the spec
        self.detectors = detectors if detectors is not None else default_detectors()
        self.pack_version = pack_version
        self.profile = profile
        self.presence_only = presence_only
        self.timeout = timeout
        self._spec: dict | None = None

    # ── SDK contract ─────────────────────────────────────────────────────────
    def test(self) -> ConnectorTest:
        try:
            spec = self._load()
        except Exception as e:  # noqa: BLE001
            return ConnectorTest(ok=False, detail=f"could not load spec: {e}")
        if not isinstance(spec, dict) or not self._schemas(spec):
            return ConnectorTest(ok=False, detail="no components.schemas / definitions found")
        return ConnectorTest(ok=True, detail=f"{len(self._schemas(spec))} schema(s) found")

    def enumerate(self) -> Iterable[ScanUnit]:
        spec = self._load()
        for name in self._schemas(spec):
            yield ScanUnit(kind="table", key=f"schema:{name}", meta={"schema_name": name})

    def scan_unit(self, unit: ScanUnit) -> list[Finding]:
        spec = self._load()
        name = unit.meta.get("schema_name") or unit.key.removeprefix("schema:")
        schema = self._schemas(spec).get(name, {})
        props = schema.get("properties") or {}
        findings: list[Finding] = []
        for prop_name, prop in props.items():
            values = self._example_values(prop)
            fs = evaluate_column(
                self.detectors, prop_name, values,
                data_type=prop.get("type") if isinstance(prop, dict) else None,
                schema="api", table=name,
                profile=ScanProfile.QUICK if not values else self.profile,
                pack_version=self.pack_version)
            for f in fs:
                # Address the finding to the API schema plane for a readable locator.
                f.locator = Locator(kind="database", schema="api", table=name,
                                    column=prop_name)
            findings.extend(fs)
        if self.presence_only:
            for f in findings:
                f.evidence = []
        return apply_cooccurrence(findings)

    def scan_all(self) -> list[Finding]:
        out: list[Finding] = []
        for unit in self.enumerate():
            out.extend(self.scan_unit(unit))
        return out

    # ── internals ──────────────────────────────────────────────────────────────
    def _load(self) -> dict:
        if self._spec is not None:
            return self._spec
        raw = self._read_source()
        self._spec = self._parse(raw)
        return self._spec

    def _read_source(self) -> str:
        if self.source.startswith(("http://", "https://")):
            req = urllib.request.Request(self.source, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                return resp.read().decode("utf-8", errors="replace")
        if not os.path.isfile(self.source):
            raise FileNotFoundError(self.source)
        with open(self.source, "rb") as fh:
            return fh.read().decode("utf-8", errors="replace")

    @staticmethod
    def _parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            import yaml  # PyYAML is a worker dependency
            return yaml.safe_load(raw)

    @staticmethod
    def _schemas(spec: dict) -> dict:
        comps = (spec.get("components") or {}).get("schemas")
        if isinstance(comps, dict):
            return comps
        defs = spec.get("definitions")          # Swagger 2.0
        return defs if isinstance(defs, dict) else {}

    @staticmethod
    def _example_values(prop: Any) -> list:
        if not isinstance(prop, dict):
            return []
        out: list = []
        for key in ("example", "default"):
            if key in prop and prop[key] is not None:
                out.append(prop[key])
        if isinstance(prop.get("enum"), list):
            out.extend(e for e in prop["enum"] if e is not None)
        return [str(v) for v in out]
