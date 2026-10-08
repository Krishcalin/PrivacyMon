"""Build the right connector for a data source (SRS FR-2.9).

Pure and Celery-free, so the API and tests import it without the broker libraries.
Credential handling is minimal for v1: a Postgres source carries a dev ``dsn`` in its
(secret-free) connection JSON; once the vault lands (SRS 7.1) the DSN is assembled
from ``connection`` + a resolved ``credential_ref`` instead.
"""
from __future__ import annotations

from urllib.parse import quote

from dpia_core.models import ScanProfile
from platform_db import crypto
from platform_db.enums import DataSourceKind
from worker.connectors.base import Connector
from worker.connectors.git import GitConnector
from worker.connectors.postgres import PostgresConnector


def _postgres_dsn(conn: dict, credential_ref: str | None) -> str:
    """Assemble a read-only DSN from the stored (secret-free) connection plus the
    decrypted password. A dev ``dsn`` in the connection is honoured as-is."""
    if conn.get("dsn"):
        return conn["dsn"]
    host = conn.get("host")
    user = conn.get("username")
    if not host or not user:
        raise ValueError(
            "postgres data source requires connection.dsn, or host + username "
            "(with the read-only password in an encrypted credential_ref)")
    password = crypto.resolve_secret(credential_ref) if credential_ref else ""
    port = conn.get("port", 5432)
    database = conn.get("database") or conn.get("dbname") or "postgres"
    auth = quote(str(user)) + (f":{quote(str(password))}" if password else "")
    return f"postgresql://{auth}@{host}:{port}/{database}"


def build_connector(data_source, *, profile: ScanProfile = ScanProfile.STANDARD
                    ) -> Connector:
    kind = data_source.kind
    conn = data_source.connection or {}
    credential_ref = getattr(data_source, "credential_ref", None)
    if kind == DataSourceKind.GIT:
        path = conn.get("path")
        if not path:
            raise ValueError("git data source requires connection.path")
        return GitConnector(path)
    if kind == DataSourceKind.POSTGRES:
        return PostgresConnector(
            _postgres_dsn(conn, credential_ref), profile=profile,
            presence_only=bool(conn.get("presence_only")))
    raise NotImplementedError(f"no connector for data source kind {kind!r}")
