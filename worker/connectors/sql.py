"""Cross-dialect SQL connector (SRS FR-2.3/2.4) — MySQL, Oracle, SQL Server.

One connector for the non-PostgreSQL engines, built on SQLAlchemy reflection so the
enumerate/sample/detect flow is identical across dialects; only the driver URL and the
set of system schemas differ. It is read-only by behaviour (it issues only SELECTs),
runs on the admin-supplied read-only account, and feeds the SAME presence-only
detection as every other connector (``detect.scan_columns``). PostgreSQL keeps its own
psycopg connector; everything else routes here.

Sampled values are read transiently to recognise the pattern and discarded. No value —
not even a masked fragment — leaves the target in presence-only mode.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.sql import column as sa_column
from sqlalchemy.sql import table as sa_table

from dpia_core.detectors.registry import DEFAULT_PACK_VERSION, default_detectors
from dpia_core.models import Finding, ScanProfile
from worker.connectors import detect
from worker.connectors.base import ConnectorTest, ScanUnit

# Schemas (or databases/owners) that are never application data, per dialect.
SYSTEM_SCHEMAS: dict[str, frozenset[str]] = {
    "postgresql": frozenset({"pg_catalog", "information_schema", "pg_toast"}),
    "mysql": frozenset({"information_schema", "mysql", "performance_schema", "sys"}),
    "mssql": frozenset({"sys", "INFORMATION_SCHEMA", "guest", "db_owner",
                        "db_accessadmin", "db_securityadmin", "db_ddladmin",
                        "db_backupoperator", "db_datareader", "db_datawriter",
                        "db_denydatareader", "db_denydatawriter"}),
    "oracle": frozenset({
        "SYS", "SYSTEM", "XDB", "CTXSYS", "MDSYS", "OUTLN", "DBSNMP", "APPQOSSYS",
        "GSMADMIN_INTERNAL", "ORDDATA", "ORDSYS", "OLAPSYS", "WMSYS", "LBACSYS",
        "DVSYS", "AUDSYS", "DBSFWUSER", "REMOTE_SCHEDULER_AGENT", "GGSYS", "ANONYMOUS",
        "XS$NULL", "OJVMSYS", "DIP", "ORACLE_OCM", "SYSBACKUP", "SYSDG", "SYSKM",
        "SYSRAC", "SYS$UMF", "FLOWS_FILES", "APEX_PUBLIC_USER", "MDDATA",
    }),
}

_DEFAULT_SAMPLE_CAP = 200


class SqlConnector:
    """Scan a MySQL / Oracle / SQL Server target into findings (SDK contract)."""

    def __init__(
        self,
        url: Any,
        *,
        detectors=None,
        pack_version: str = DEFAULT_PACK_VERSION,
        profile: ScanProfile = ScanProfile.STANDARD,
        sample_cap: int = _DEFAULT_SAMPLE_CAP,
        presence_only: bool = False,
        create_engine_fn: Callable[[Any], Any] | None = None,
    ):
        self.url = url
        self.detectors = detectors if detectors is not None else default_detectors()
        self.pack_version = pack_version
        self.profile = profile
        self.sample_cap = sample_cap if profile != ScanProfile.DEEP else max(sample_cap, 1000)
        self.presence_only = presence_only
        self._make_engine = create_engine_fn or (
            lambda u: create_engine(u, pool_pre_ping=True))
        self._engine = None

    def _engine_(self):
        if self._engine is None:
            self._engine = self._make_engine(self.url)
        return self._engine

    def _dialect(self) -> str:
        return self._engine_().dialect.name

    # ── SDK contract ─────────────────────────────────────────────────────────
    def test(self) -> ConnectorTest:
        try:
            with self._engine_().connect() as conn:
                conn.execute(text("SELECT 1"))
            return ConnectorTest(ok=True, detail=f"read-only connection ok ({self._dialect()})")
        except Exception as e:  # noqa: BLE001 — report, never raise
            return ConnectorTest(ok=False, detail=f"connect failed: {e}")

    def enumerate(self) -> Iterable[ScanUnit]:
        insp = inspect(self._engine_())
        system = SYSTEM_SCHEMAS.get(self._dialect(), frozenset())
        for schema in insp.get_schema_names():
            if schema in system:
                continue
            tables = list(insp.get_table_names(schema=schema))
            try:
                tables += list(insp.get_view_names(schema=schema))
            except Exception:  # noqa: BLE001 — some dialects/grants lack view listing
                pass
            for table in tables:
                try:
                    cols = insp.get_columns(table, schema=schema)
                except Exception:  # noqa: BLE001 — unreadable table -> skip, never crash
                    continue
                columns = [{"name": c["name"], "data_type": str(c.get("type"))}
                           for c in cols]
                if columns:
                    yield ScanUnit(kind="table", key=f"{schema}.{table}",
                                   meta={"schema": schema, "table": table,
                                         "columns": columns})

    def scan_unit(self, unit: ScanUnit) -> list[Finding]:
        schema = unit.meta["schema"]
        table = unit.meta["table"]
        columns = unit.meta["columns"]
        rows: list[tuple] = []
        if self.profile != ScanProfile.QUICK:
            rows = self._sample(schema, table, [c["name"] for c in columns])
        return detect.scan_columns(
            self.detectors, schema, table, columns, rows,
            profile=self.profile, pack_version=self.pack_version,
            presence_only=self.presence_only)

    # ── internals ──────────────────────────────────────────────────────────────
    def _sample(self, schema: str, table: str, column_names: list[str]) -> list[tuple]:
        # A lightweight, dialect-compiled SELECT: SQLAlchemy renders LIMIT / TOP /
        # FETCH FIRST n ROWS ONLY per engine, and quotes identifiers correctly.
        tbl = sa_table(table, *[sa_column(c) for c in column_names], schema=schema)
        stmt = select(tbl).limit(self.sample_cap)
        with self._engine_().connect() as conn:
            return [tuple(r) for r in conn.execute(stmt).fetchall()]
