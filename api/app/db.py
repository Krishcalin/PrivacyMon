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

from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import text

from platform_db.session import (
    make_sync_engine, make_sync_sessionmaker, set_rls_context_sync,
)

from .settings import settings


@lru_cache(maxsize=1)
def get_engine():
    """The OWNER engine — used for writes and admin/auth lookups (bypasses RLS)."""
    return make_sync_engine(settings.database_url)


@lru_cache(maxsize=1)
def get_sessionmaker():
    return make_sync_sessionmaker(get_engine())


@lru_cache(maxsize=1)
def get_scoped_engine():
    """The RESTRICTED-role engine (privacymon_app) — RLS applies to its queries."""
    return make_sync_engine(settings.app_database_url)


@lru_cache(maxsize=1)
def get_scoped_sessionmaker():
    return make_sync_sessionmaker(get_scoped_engine())


@contextmanager
def scoped_session(principal):
    """A session as the restricted role with the RLS context set from ``principal``,
    so a read returns only the applications the caller may see (a global role bypasses).
    Owners and operators are confined to their application ids by the database itself,
    not merely by an API filter (SRS 8.5 / 11.1)."""
    s = get_scoped_sessionmaker()()
    try:
        set_rls_context_sync(s, principal.application_ids, bypass=principal.is_global)
        yield s
    finally:
        s.close()


def db_ok() -> tuple[bool, str]:
    """Readiness probe for PostgreSQL (SRS 9 /readyz). Never raises."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as e:                       # noqa: BLE001 — report, never crash readyz
        return False, f"unavailable: {type(e).__name__}"
