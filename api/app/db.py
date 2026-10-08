"""API database access (platform DB, SRS section 8).

A lazily-built synchronous engine so importing the app never opens a connection (the
test suite and ``--help`` must not need a database). The engine is created on first
use from ``settings.database_url``.

This slice connects as the configured role for reads; once SSO auth lands, the API
will connect as the non-superuser ``privacymon_app`` role and set the per-request
row-level-security context (SRS 8.5) so a query is scoped to the caller's
applications. The worker remains the privileged writer.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import text

from platform_db.session import make_sync_engine, make_sync_sessionmaker

from .settings import settings


@lru_cache(maxsize=1)
def get_engine():
    return make_sync_engine(settings.database_url)


@lru_cache(maxsize=1)
def get_sessionmaker():
    return make_sync_sessionmaker(get_engine())


def db_ok() -> tuple[bool, str]:
    """Readiness probe for PostgreSQL (SRS 9 /readyz). Never raises."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as e:                       # noqa: BLE001 — report, never crash readyz
        return False, f"unavailable: {type(e).__name__}"
