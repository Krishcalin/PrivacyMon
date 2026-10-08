"""Declarative base, metadata naming convention, and the common mixins.

The naming convention is load-bearing: it gives every index, constraint and key a
deterministic name so Alembic autogenerate produces stable migrations and the
baseline can be hand-audited. ``UUIDPKMixin`` and ``TimestampMixin`` encode the two
SRS section 8 invariants — UUID v7 keys and the created/updated audit quartet on
every mutable table.
"""
from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from platform_db.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


class UUIDPKMixin:
    """A UUID v7 primary key named ``id``, minted application-side (see ids.py)."""

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid7)


class TimestampMixin:
    """The SRS section 8 audit quartet carried by every mutable table.

    ``created_by`` / ``updated_by`` reference ``users.id`` and are nullable: rows
    created by a system process (a JIT-provisioned user, a scheduled scan) have no
    acting user, and the FK is ``SET NULL`` so deactivating a user never deletes the
    history of what they touched.
    """

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True)
