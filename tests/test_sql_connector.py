"""Cross-dialect SQL connector — structural (the live path is covered end-to-end by a
MySQL target scan; Oracle and SQL Server use the identical code path)."""
from __future__ import annotations

from dpia_core.models import ScanProfile
from worker.connectors.sql import SYSTEM_SCHEMAS, SqlConnector


def test_system_schemas_cover_the_four_dialects():
    assert {"postgresql", "mysql", "oracle", "mssql"} <= set(SYSTEM_SCHEMAS)
    assert "information_schema" in SYSTEM_SCHEMAS["mysql"]
    assert "SYS" in SYSTEM_SCHEMAS["oracle"]
    assert "sys" in SYSTEM_SCHEMAS["mssql"]


def test_engine_is_lazy_and_flags_carry():
    # Constructing must not open a connection (create_engine_fn is never called).
    c = SqlConnector("mysql+pymysql://u:p@h/db", presence_only=True,
                     create_engine_fn=lambda _: (_ for _ in ()).throw(AssertionError))
    assert c.presence_only is True


def test_deep_profile_raises_the_sample_cap():
    c = SqlConnector("x", profile=ScanProfile.DEEP, create_engine_fn=lambda _: None)
    assert c.sample_cap >= 1000
