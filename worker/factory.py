"""Build the right connector for a data source (SRS FR-2.9).

Pure and Celery-free, so the API and tests import it without the broker libraries.
Credential handling is minimal for v1: a Postgres source carries a dev ``dsn`` in its
(secret-free) connection JSON; once the vault lands (SRS 7.1) the DSN is assembled
from ``connection`` + a resolved ``credential_ref`` instead.
"""
from __future__ import annotations

from dpia_core.models import ScanProfile
from platform_db.enums import DataSourceKind
from worker.connectors.base import Connector
from worker.connectors.git import GitConnector
from worker.connectors.postgres import PostgresConnector


def build_connector(data_source, *, profile: ScanProfile = ScanProfile.STANDARD
                    ) -> Connector:
    kind = data_source.kind
    conn = data_source.connection or {}
    if kind == DataSourceKind.GIT:
        path = conn.get("path")
        if not path:
            raise ValueError("git data source requires connection.path")
        return GitConnector(path)
    if kind == DataSourceKind.POSTGRES:
        dsn = conn.get("dsn")
        if not dsn:
            raise ValueError(
                "postgres data source requires connection.dsn (v1; credential vault later)")
        return PostgresConnector(dsn, profile=profile)
    raise NotImplementedError(f"no connector for data source kind {kind!r}")
