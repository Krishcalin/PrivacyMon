"""Registry group (SRS 8.1): business units, applications, data sources."""
from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_db import enums
from platform_db.base import Base, TimestampMixin, UUIDPKMixin


class BusinessUnit(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "business_units"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True)

    parent: Mapped["BusinessUnit | None"] = relationship(
        remote_side="BusinessUnit.id", backref="children")


class Application(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        # GIN index for tag filtering (SRS 8.1 / FR-1.3).
        Index("ix_applications_tags", "tags", postgresql_using="gin"),
        Index("ix_applications_business_unit_id", "business_unit_id"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tech_contact_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    environment: Mapped[enums.Environment] = mapped_column(
        enums.environment_enum, nullable=False)
    hosting: Mapped[enums.Hosting] = mapped_column(enums.hosting_enum, nullable=False)
    internet_facing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    user_base: Mapped[enums.UserBase | None] = mapped_column(
        enums.user_base_enum, nullable=True)
    approx_records: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    lifecycle: Mapped[enums.Lifecycle] = mapped_column(
        enums.lifecycle_enum, nullable=False, default=enums.Lifecycle.DRAFT)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}")

    data_sources: Mapped[list["DataSource"]] = relationship(
        back_populates="application", cascade="all, delete-orphan")


class DataSource(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"
    __table_args__ = (Index("ix_data_sources_application_id", "application_id"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    kind: Mapped[enums.DataSourceKind] = mapped_column(
        enums.data_source_kind_enum, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Connection parameters WITHOUT secrets (host, port, db, options); the secret is
    # referenced by `credential_ref` (a vault path or an envelope-encrypted key id),
    # never stored here — SRS 8.1 / 11.2.
    connection: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}")
    credential_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    scan_profile_default: Mapped[enums.ScanProfile] = mapped_column(
        enums.scan_profile_enum, nullable=False, default=enums.ScanProfile.STANDARD)
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Soft pointer to the most recent scan job (not an FK: scan_jobs references
    # data_sources, so a hard FK here would be circular; the job row is the source of
    # truth for the relationship).
    last_scan_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True)

    application: Mapped["Application"] = relationship(back_populates="data_sources")
