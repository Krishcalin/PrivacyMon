"""Scanning group (SRS 8.2): detector packs, detectors, scan jobs/units,
findings (partitioned), suppressions, inventory."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_db import enums
from platform_db.base import Base, TimestampMixin, UUIDPKMixin
from platform_db.ids import uuid7


class DetectorPack(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "detector_packs"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_detector_packs_name_version"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[enums.DetectorPackSource] = mapped_column(
        enums.detector_pack_source_enum, nullable=False,
        default=enums.DetectorPackSource.BUILTIN)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict,
                                           server_default="{}")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Detector(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "detectors"
    __table_args__ = (Index("ix_detectors_pack_id", "pack_id"),)

    pack_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("detector_packs.id", ondelete="CASCADE"),
        nullable=False)
    category: Mapped[enums.Category] = mapped_column(enums.category_enum, nullable=False)
    tier: Mapped[enums.Tier] = mapped_column(enums.tier_enum, nullable=False)
    pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    validator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_positive: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}")
    context_negative: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}")
    base_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)


class ScanJob(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "scan_jobs"
    __table_args__ = (
        Index("ix_scan_jobs_application_id", "application_id"),
        Index("ix_scan_jobs_data_source_id", "data_source_id"),
        Index("ix_scan_jobs_state", "state"),
    )

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    profile: Mapped[enums.ScanProfile] = mapped_column(
        enums.scan_profile_enum, nullable=False)
    state: Mapped[enums.ScanState] = mapped_column(
        enums.scan_state_enum, nullable=False, default=enums.ScanState.QUEUED)
    started_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    units_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ScanUnit(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "scan_units"
    __table_args__ = (Index("ix_scan_units_scan_job_id", "scan_job_id"),)

    scan_job_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("scan_jobs.id", ondelete="CASCADE"),
        nullable=False)
    kind: Mapped[enums.ScanUnitKind] = mapped_column(
        enums.scan_unit_kind_enum, nullable=False)
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[enums.ScanState] = mapped_column(
        enums.scan_state_enum, nullable=False, default=enums.ScanState.QUEUED)
    rows_sampled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Finding(TimestampMixin, Base):
    """A detected PII instance (SRS 8.2).

    LIST-partitioned by ``scan_job_id`` (one partition per job, created at job start,
    detached for archival) so a retention sweep is a cheap DETACH rather than a mass
    DELETE. PostgreSQL requires the partition key in every unique/primary key, so the
    primary key is composite ``(id, scan_job_id)`` — ``id`` is still globally unique in
    practice (UUID v7) and is how the API addresses a finding.
    """

    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_application_id_category_tier",
              "application_id", "category", "tier"),
        Index("ix_findings_locator", "locator", postgresql_using="gin"),
        Index("ix_findings_review_state", "review_state"),
        {"postgresql_partition_by": "LIST (scan_job_id)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid7)
    scan_job_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("scan_jobs.id", ondelete="CASCADE"),
        primary_key=True, nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    category: Mapped[enums.Category] = mapped_column(enums.category_enum, nullable=False)
    tier: Mapped[enums.Tier] = mapped_column(enums.tier_enum, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    hit_rate: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0)
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False)
    protection_state: Mapped[enums.ProtectionState] = mapped_column(
        enums.protection_state_enum, nullable=False,
        default=enums.ProtectionState.UNKNOWN)
    combined_identity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list,
                                           server_default="[]")  # max 3 masked snippets
    detector_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    pack_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    review_state: Mapped[enums.ReviewState] = mapped_column(
        enums.review_state_enum, nullable=False, default=enums.ReviewState.NEW)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    suppression_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True)


class Suppression(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "suppressions"
    __table_args__ = (Index("ix_suppressions_application_id", "application_id"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    locator_match: Mapped[dict] = mapped_column(JSONB, nullable=False)
    category: Mapped[enums.Category | None] = mapped_column(
        enums.category_enum, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class Inventory(UUIDPKMixin, TimestampMixin, Base):
    """One row per application × category, rebuilt at scan end; owner-annotated
    columns (purpose, source_of_data, recipients) are preserved across rebuilds."""

    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("application_id", "category",
                         name="uq_inventory_application_id_category"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    category: Mapped[enums.Category] = mapped_column(enums.category_enum, nullable=False)
    tier: Mapped[enums.Tier] = mapped_column(enums.tier_enum, nullable=False)
    locations_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_estimate: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    protection_state_summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}")
    readers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict,
                                          server_default="{}")
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_of_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipients: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
