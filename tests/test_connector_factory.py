"""Connector factory (SRS FR-2.9) — no database or broker needed."""
from __future__ import annotations

import os

import pytest

from platform_db.enums import DataSourceKind
from worker.connectors.git import GitConnector
from worker.connectors.postgres import PostgresConnector
from worker.factory import build_connector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "fixtures", "repo")


class _DataSource:
    """A stand-in for the ORM row — build_connector reads only kind and connection."""

    def __init__(self, kind, connection):
        self.kind = kind
        self.connection = connection


def test_git_data_source_builds_a_git_connector():
    c = build_connector(_DataSource(DataSourceKind.GIT, {"path": FIXTURE}))
    assert isinstance(c, GitConnector)


def test_postgres_data_source_builds_a_postgres_connector():
    c = build_connector(_DataSource(
        DataSourceKind.POSTGRES, {"dsn": "postgresql://u:p@h:5432/db"}))
    assert isinstance(c, PostgresConnector)


def test_git_without_a_path_is_a_clear_error():
    with pytest.raises(ValueError, match="connection.path"):
        build_connector(_DataSource(DataSourceKind.GIT, {}))


def test_postgres_without_a_dsn_is_a_clear_error():
    with pytest.raises(ValueError, match="connection.dsn"):
        build_connector(_DataSource(DataSourceKind.POSTGRES, {}))


def test_unimplemented_kind_is_reported():
    with pytest.raises(NotImplementedError):
        build_connector(_DataSource(DataSourceKind.OPENAPI, {"dsn": "x"}))


def test_postgres_target_builds_dsn_from_parts_and_encrypted_credential(monkeypatch):
    from platform_db import crypto
    key = crypto.new_master_key()
    monkeypatch.setenv("PRIVACYMON_MASTER_KEY", key)
    ref = crypto.encrypt_secret("ro-pass", key=key)
    ds = _DataSource(DataSourceKind.POSTGRES, {
        "host": "10.0.0.5", "port": 5432, "database": "appdb",
        "username": "scan_ro", "presence_only": True})
    ds.credential_ref = ref
    c = build_connector(ds)
    assert isinstance(c, PostgresConnector)
    assert c.presence_only is True
    assert c.dsn == "postgresql://scan_ro:ro-pass@10.0.0.5:5432/appdb"


def _target_ds(kind, *, database="appdb", port=None):
    conn = {"host": "10.0.0.9", "database": database, "username": "scan_ro",
            "presence_only": True}
    if port:
        conn["port"] = port
    ds = _DataSource(kind, conn)
    return ds


def test_mysql_oracle_mssql_build_sql_connectors_with_right_urls(monkeypatch):
    from platform_db import crypto
    from worker.connectors.sql import SqlConnector
    key = crypto.new_master_key()
    monkeypatch.setenv("PRIVACYMON_MASTER_KEY", key)
    ref = crypto.encrypt_secret("ro-pass", key=key)

    for ds in (_target_ds(DataSourceKind.MYSQL), _target_ds(DataSourceKind.ORACLE),
               _target_ds(DataSourceKind.MSSQL)):
        ds.credential_ref = ref
        c = build_connector(ds)
        assert isinstance(c, SqlConnector) and c.presence_only is True

    my = _target_ds(DataSourceKind.MYSQL)
    my.credential_ref = ref
    assert build_connector(my).url.drivername == "mysql+pymysql"
    assert build_connector(my).url.port == 3306            # default port applied

    orc = _target_ds(DataSourceKind.ORACLE)
    orc.credential_ref = ref
    url = build_connector(orc).url
    assert url.drivername == "oracle+oracledb" and url.port == 1521
    assert url.query["service_name"] == "appdb"            # Oracle uses service name

    ms = _target_ds(DataSourceKind.MSSQL, port=1444)
    ms.credential_ref = ref
    url = build_connector(ms).url
    assert url.drivername == "mssql+pymssql" and url.port == 1444 and url.password == "ro-pass"
