"""platform_db — PrivacyMon's own PostgreSQL persistence layer (SRS section 8).

Shared by the API and the worker; deliberately SEPARATE from ``dpia_core``, which
stays dependency-free (no SQLAlchemy, no DB). This package owns the SQLAlchemy 2.0
(async, psycopg 3) models for the four table groups — registry, scanning,
assessment, platform — plus the row-level-security contract, the UUID v7 key
generator, and the Alembic migrations.

Importing :data:`Base` gives the populated ``MetaData`` (every model module is
imported here), which is what Alembic's ``env.py`` targets.
"""
from __future__ import annotations

from platform_db.base import Base, TimestampMixin, metadata
from platform_db.ids import uuid7
from platform_db import models  # noqa: F401  — populates Base.metadata

__all__ = ["Base", "TimestampMixin", "metadata", "uuid7", "models"]
