"""PostgreSQL connector (SRS FR-2.3 / FR-2.4 / FR-2.5).

Connects READ-ONLY to a target PostgreSQL, enumerates user schemas/tables/columns
(with data types, comments and a row estimate), samples a capped number of rows per
table, and runs ``evaluate_column`` per column — so a column named ``aadhaar`` and a
column whose sampled values look like Aadhaar numbers both surface, with a
schema.table.column locator. Sampled values are used transiently and never persisted;
only masked evidence leaves the engine (SRS 4.5 / 11.3).

Safety (FR-3.7): the session is read-only with a statement timeout and a bounded
sample, so a scan cannot write to or heavily load a production database. The detection
logic (`_rows_to_findings`) is separated from I/O so it is unit-testable without a
live database; the live path is covered by an integration test gated on a target DSN.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from dpia_core.detectors.registry import DEFAULT_PACK_VERSION, default_detectors
from dpia_core.engine import apply_cooccurrence, evaluate_column
from dpia_core.models import Finding, ScanProfile
from worker.connectors.base import ConnectorTest, ScanUnit

# Schemas that are never application data.
SYSTEM_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})

_DEFAULT_SAMPLE_CAP = 200
_STATEMENT_TIMEOUT_MS = 30_000


class PostgresConnector:
    """Scan a target PostgreSQL database into findings (SDK contract)."""

    def __init__(
        self,
        dsn: str,
        *,
        detectors=None,
        pack_version: str = DEFAULT_PACK_VERSION,
        profile: ScanProfile = ScanProfile.STANDARD,
        sample_cap: int = _DEFAULT_SAMPLE_CAP,
        schemas_exclude: frozenset[str] = SYSTEM_SCHEMAS,
        connect: Callable[[str], Any] | None = None,
    ):
        self.dsn = dsn
        self.detectors = detectors if detectors is not None else default_detectors()
        self.pack_version = pack_version
        self.profile = profile
        self.sample_cap = sample_cap if profile != ScanProfile.DEEP else max(sample_cap, 1000)
        self.schemas_exclude = schemas_exclude
        self._connect = connect or _default_connect

    # ── SDK contract ─────────────────────────────────────────────────────────
    def test(self) -> ConnectorTest:
        try:
            conn = self._connect(self.dsn)
        except Exception as e:                       # noqa: BLE001 — report, never raise
            return ConnectorTest(ok=False, detail=f"connect failed: {e}")
        try:
            self._prepare(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return ConnectorTest(ok=True, detail="read-only connection ok")
        except Exception as e:                       # noqa: BLE001
            return ConnectorTest(ok=False, detail=f"probe failed: {e}")
        finally:
            _safe_close(conn)

    def enumerate(self) -> Iterable[ScanUnit]:
        conn = self._connect(self.dsn)
        try:
            self._prepare(conn)
            tables = self._load_columns(conn)
        finally:
            _safe_close(conn)
        for (schema, table), columns in tables.items():
            if schema in self.schemas_exclude:
                continue
            yield ScanUnit(kind="table", key=f"{schema}.{table}",
                           meta={"schema": schema, "table": table, "columns": columns})

    def scan_unit(self, unit: ScanUnit) -> list[Finding]:
        schema = unit.meta["schema"]
        table = unit.meta["table"]
        columns = unit.meta["columns"]              # [{name, data_type, comment}]
        rows: list[tuple] = []
        if self.profile != ScanProfile.QUICK:
            conn = self._connect(self.dsn)
            try:
                self._prepare(conn)
                rows = self._sample(conn, schema, table, [c["name"] for c in columns])
            finally:
                _safe_close(conn)
        return self._rows_to_findings(schema, table, columns, rows)

    # ── pure detection (no I/O — unit-testable) ───────────────────────────────
    def _rows_to_findings(self, schema: str, table: str,
                          columns: list[dict], rows: list[tuple]) -> list[Finding]:
        findings: list[Finding] = []
        for idx, col in enumerate(columns):
            values = [r[idx] for r in rows] if rows else []
            findings.extend(evaluate_column(
                self.detectors, col["name"], values,
                data_type=col.get("data_type"), schema=schema, table=table,
                profile=self.profile, pack_version=self.pack_version))
        return apply_cooccurrence(findings)

    # ── grants (FR-2.5) ────────────────────────────────────────────────────────
    def table_grants(self, schema: str, table: str) -> list[str]:
        """Roles with SELECT on the table, so the inventory can show who can read it."""
        conn = self._connect(self.dsn)
        try:
            self._prepare(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT grantee FROM information_schema.role_table_grants "
                    "WHERE table_schema = %s AND table_name = %s "
                    "AND privilege_type = 'SELECT' ORDER BY grantee",
                    (schema, table))
                return [r[0] for r in cur.fetchall()]
        finally:
            _safe_close(conn)

    # ── internals ──────────────────────────────────────────────────────────────
    def _prepare(self, conn) -> None:
        """Make the session read-only and time-bounded (FR-3.7) so a scan cannot write
        to or stall a production database."""
        try:
            conn.autocommit = True
        except Exception:                            # noqa: BLE001 — fakes may lack it
            pass
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
            cur.execute(f"SET statement_timeout = {_STATEMENT_TIMEOUT_MS}")

    def _load_columns(self, conn) -> dict[tuple[str, str], list[dict]]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.table_schema, c.table_name, c.column_name, c.data_type, "
                "       col_description(pgc.oid, c.ordinal_position) AS comment "
                "FROM information_schema.columns c "
                "JOIN pg_class pgc ON pgc.relname = c.table_name "
                "JOIN pg_namespace pgn ON pgn.oid = pgc.relnamespace "
                "      AND pgn.nspname = c.table_schema "
                "WHERE c.table_schema NOT IN ('pg_catalog','information_schema','pg_toast') "
                "ORDER BY c.table_schema, c.table_name, c.ordinal_position")
            out: dict[tuple[str, str], list[dict]] = {}
            for schema, table, column, data_type, comment in cur.fetchall():
                out.setdefault((schema, table), []).append(
                    {"name": column, "data_type": data_type, "comment": comment})
            return out

    def _sample(self, conn, schema: str, table: str, column_names: list[str]) -> list[tuple]:
        from psycopg import sql
        cols = sql.SQL(", ").join(sql.Identifier(c) for c in column_names)
        query = sql.SQL("SELECT {cols} FROM {sch}.{tbl} LIMIT {cap}").format(
            cols=cols, sch=sql.Identifier(schema), tbl=sql.Identifier(table),
            cap=sql.Literal(self.sample_cap))
        with conn.cursor() as cur:
            cur.execute(query)
            return list(cur.fetchall())


def _default_connect(dsn: str):
    import psycopg
    return psycopg.connect(dsn)


def _safe_close(conn) -> None:
    try:
        conn.close()
    except Exception:                                # noqa: BLE001
        pass
