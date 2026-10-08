"""Platform group (SRS 8.4): users, user roles, API tokens, audit log,
webhooks, settings.

(Named ``platform_tables`` rather than ``platform`` to avoid shadowing the stdlib
``platform`` module.)
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_db import enums
from platform_db.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    """Provisioned on first SSO login (JIT) — SRS 8.4."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("idp_subject", name="uq_users_idp_subject"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    idp_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserRole(UUIDPKMixin, TimestampMixin, Base):
    """A role grant. ``application_id`` NULL means a global role (Admin, DPO,
    Auditor); a non-null value scopes the role (Owner, Operator) to one application."""

    __tablename__ = "user_roles"
    __table_args__ = (
        # NULLs are distinct in a plain UNIQUE, so split into two partial uniques:
        # one global grant per (user, role), one scoped grant per (user, role, app).
        Index("uq_user_roles_global", "user_id", "role", unique=True,
              postgresql_where=text("application_id IS NULL")),
        Index("uq_user_roles_scoped", "user_id", "role", "application_id", unique=True,
              postgresql_where=text("application_id IS NOT NULL")),
        Index("ix_user_roles_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[enums.Role] = mapped_column(enums.role_enum, nullable=False)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=True)


class ApiToken(UUIDPKMixin, TimestampMixin, Base):
    """CI/CD and integration tokens (SRS 8.4). Only the hash is stored."""

    __tablename__ = "api_tokens"
    __table_args__ = (
        UniqueConstraint("hashed_token", name="uq_api_tokens_hashed_token"),
        Index("ix_api_tokens_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_token: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}")
    expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(UUIDPKMixin, Base):
    """Append-only (SRS 8.4): a trigger (added in the migration) rejects UPDATE and
    DELETE, and only INSERT is granted to the application role. No update quartet — an
    append-only log records ``at`` and ``actor_id`` and is never mutated."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_object", "object_type", "object_id"),
        Index("ix_audit_log_actor_id", "actor_id"),
        Index("ix_audit_log_at", "at"),
    )

    at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Webhook(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "webhooks"

    event_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Setting(Base):
    """Key/value platform settings: thresholds, risk bands, retention, SDF flag."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
