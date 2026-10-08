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
        build_connector(_DataSource(DataSourceKind.ORACLE, {"dsn": "x"}))
