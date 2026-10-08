"""Async engine, session factory, and the per-request RLS context setter.

The driver is psycopg 3 (``postgresql+psycopg://``), which SQLAlchemy 2 drives
asynchronously — no asyncpg. Nothing here connects at import time; the API/worker
build the engine from configuration at startup.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from platform_db.ddl import SESSION_VAR_APP_IDS, SESSION_VAR_BYPASS


def normalise_async_url(url: str) -> str:
    """Accept a plain ``postgresql://`` URL and point it at the async psycopg driver."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def normalise_sync_url(url: str) -> str:
    """Point a URL at the SYNC psycopg 3 driver (the worker and Alembic use sync)."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    # a +asyncpg/+psycopg_async URL would be wrong for a sync engine; leave psycopg as-is
    return url


def make_sync_engine(url: str, *, echo: bool = False, pool_size: int = 5) -> Engine:
    """A synchronous psycopg 3 engine — for the worker/pipeline and scripts."""
    return create_engine(normalise_sync_url(url), echo=echo, pool_size=pool_size,
                         pool_pre_ping=True)


def make_sync_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, class_=Session)


def make_engine(url: str, *, echo: bool = False, pool_size: int = 5) -> AsyncEngine:
    return create_async_engine(
        normalise_async_url(url), echo=echo, pool_size=pool_size, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def set_rls_context(
    session: AsyncSession,
    application_ids: Iterable[uuid.UUID | str] | None,
    *,
    bypass: bool = False,
) -> None:
    """Set the row-level-security GUCs for the current transaction (SRS 8.5).

    The API calls this in the auth dependency after resolving the caller's
    per-application roles. ``bypass=True`` is for global roles (Admin, DPO, Auditor).
    Both GUCs are set LOCAL (``is_local=true``) so they vanish at transaction end and
    never leak onto the next checkout of a pooled connection.
    """
    ids = ",".join(str(a) for a in (application_ids or []))
    await session.execute(
        text("SELECT set_config(:k, :v, true)"),
        {"k": SESSION_VAR_APP_IDS, "v": ids},
    )
    await session.execute(
        text("SELECT set_config(:k, :v, true)"),
        {"k": SESSION_VAR_BYPASS, "v": "on" if bypass else "off"},
    )
