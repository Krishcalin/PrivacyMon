"""Build the right connector for a data source (SRS FR-2.9).

Pure and Celery-free, so the API and tests import it without the broker libraries.
PostgreSQL uses its dedicated psycopg connector; MySQL, Oracle and SQL Server share
the SQLAlchemy-based ``SqlConnector``. The read-only password is decrypted from the
data source's encrypted ``credential_ref`` and encoded into the connection URL; a dev
``dsn`` in the connection is honoured as-is.
"""
from __future__ import annotations

from urllib.parse import quote

from sqlalchemy.engine import URL

from dpia_core.models import ScanProfile
from platform_db import crypto
from platform_db.enums import DataSourceKind
from worker.connectors.base import Connector
from worker.connectors.filesystem import FilesystemConnector
from worker.connectors.git import GitConnector
from worker.connectors.openapi import OpenApiConnector
from worker.connectors.postgres import PostgresConnector
from worker.connectors.sql import SqlConnector

# SQLAlchemy driver + default port for the engines that route through SqlConnector.
_SQL_DRIVERS: dict[DataSourceKind, tuple[str, int]] = {
    DataSourceKind.MYSQL: ("mysql+pymysql", 3306),
    DataSourceKind.ORACLE: ("oracle+oracledb", 1521),
    DataSourceKind.MSSQL: ("mssql+pymssql", 1433),
}


def _require_target(conn: dict) -> tuple[str, str]:
    host, user = conn.get("host"), conn.get("username")
    if not host or not user:
        raise ValueError(
            "database data source requires connection.dsn, or host + username "
            "(with the read-only password in an encrypted credential_ref)")
    return host, user


def _postgres_dsn(conn: dict, credential_ref: str | None) -> str:
    if conn.get("dsn"):
        return conn["dsn"]
    host, user = _require_target(conn)
    password = crypto.resolve_secret(credential_ref) if credential_ref else ""
    port = conn.get("port", 5432)
    database = conn.get("database") or conn.get("dbname") or "postgres"
    auth = quote(str(user)) + (f":{quote(str(password))}" if password else "")
    return f"postgresql://{auth}@{host}:{port}/{database}"


def _sql_url(kind: DataSourceKind, conn: dict, credential_ref: str | None):
    if conn.get("dsn"):
        return conn["dsn"]
    host, user = _require_target(conn)
    password = crypto.resolve_secret(credential_ref) if credential_ref else None
    driver, default_port = _SQL_DRIVERS[kind]
    port = conn.get("port") or default_port
    database = conn.get("database") or conn.get("dbname")
    if kind == DataSourceKind.ORACLE:
        # Oracle addresses the database by service name, not a path segment.
        return URL.create(driver, username=user, password=password, host=host,
                          port=port, query={"service_name": database} if database else {})
    return URL.create(driver, username=user, password=password, host=host,
                     port=port, database=database)


def build_connector(data_source, *, profile: ScanProfile = ScanProfile.STANDARD,
                    detectors=None, pack_version: str | None = None) -> Connector:
    """Build the connector for a data source. ``detectors``/``pack_version`` override the
    built-in pack (the pipeline passes the merged built-in + custom chain here, SRS
    FR-4.7); when omitted, each connector falls back to ``default_detectors()``."""
    kind = data_source.kind
    conn = data_source.connection or {}
    credential_ref = getattr(data_source, "credential_ref", None)
    presence_only = bool(conn.get("presence_only"))
    # Only pass detector overrides when supplied, so each connector keeps its own default.
    det: dict = {}
    if detectors is not None:
        det["detectors"] = detectors
    if pack_version is not None:
        det["pack_version"] = pack_version

    if kind == DataSourceKind.GIT:
        path = conn.get("path")
        if not path:
            raise ValueError("git data source requires connection.path")
        return GitConnector(path, profile=profile, **det)
    if kind == DataSourceKind.FILESYSTEM:
        path = conn.get("path")
        if not path:
            raise ValueError("filesystem data source requires connection.path")
        return FilesystemConnector(path, profile=profile, presence_only=presence_only, **det)
    if kind == DataSourceKind.OPENAPI:
        source = conn.get("url") or conn.get("path") or conn.get("spec")
        if not source:
            raise ValueError("openapi data source requires connection.url or connection.path")
        return OpenApiConnector(source, profile=profile, presence_only=presence_only, **det)
    if kind == DataSourceKind.POSTGRES:
        return PostgresConnector(
            _postgres_dsn(conn, credential_ref), profile=profile,
            presence_only=presence_only, **det)
    if kind in _SQL_DRIVERS:
        return SqlConnector(
            _sql_url(kind, conn, credential_ref), profile=profile,
            presence_only=presence_only, **det)
    raise NotImplementedError(f"no connector for data source kind {kind!r}")
