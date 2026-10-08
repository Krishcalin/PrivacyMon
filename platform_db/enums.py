"""Enumerations for the platform schema (SRS sections 2.2, 3.1, 3.6, 4, 5, 8).

The detection/assessment enums (Tier, ProtectionState, ReviewState, Category,
DetectorKind, ScanProfile) are REUSED from ``dpia_core`` rather than redefined, so a
finding written by the engine and a finding row in Postgres can never disagree on a
label. The platform-only enums (registry attributes, workflow states, roles) live
here because ``dpia_core`` has no concept of them.

``pg_enum`` builds a native PostgreSQL ENUM whose labels are the enum *values*
(lowercase strings like ``"critical"``), matching what ``dpia_core`` serialises to
JSON — SQLAlchemy would otherwise use the member *names* (``"CRITICAL"``).
"""
from __future__ import annotations

from enum import Enum
from typing import Type

from sqlalchemy import Enum as SAEnum

# Re-exported from the dependency-free core so the DB and the engine share one source.
from dpia_core.models import (  # noqa: F401
    Category,
    DetectorKind,
    ProtectionState,
    ReviewState,
    ScanProfile,
    Tier,
)


def pg_enum(enum_cls: Type[Enum], name: str) -> SAEnum:
    """A native PG ENUM named ``name`` whose labels are the members' ``.value``."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


# ── Registry (SRS 3.1 / 8.1) ──────────────────────────────────────────────────
class Environment(str, Enum):
    PROD = "prod"
    UAT = "uat"
    DEV = "dev"


class Hosting(str, Enum):
    ON_PREM = "on_prem"
    CLOUD = "cloud"


class UserBase(str, Enum):
    EMPLOYEES = "employees"
    CUSTOMERS = "customers"
    VENDORS = "vendors"
    PUBLIC = "public"


class Lifecycle(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DECOMMISSIONED = "decommissioned"


class DataSourceKind(str, Enum):
    GIT = "git"
    POSTGRES = "postgres"
    ORACLE = "oracle"
    MSSQL = "mssql"
    MYSQL = "mysql"
    OPENAPI = "openapi"
    FILESYSTEM = "filesystem"


# ── Scanning (SRS 3.3 / 8.2) ──────────────────────────────────────────────────
class DetectorPackSource(str, Enum):
    BUILTIN = "builtin"
    CUSTOM = "custom"


class ScanState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanUnitKind(str, Enum):
    TABLE = "table"
    FILE = "file"


# ── Assessment (SRS 3.6 / 5 / 8.3) ────────────────────────────────────────────
class DpiaState(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    PUBLISHED = "published"


class Answer(str, Enum):
    YES = "yes"
    PARTIAL = "partial"
    NO = "no"
    NA = "na"


class Framework(str, Enum):
    DPDP = "dpdp"
    ISO27701 = "iso27701"
    ISO27001 = "iso27001"
    CERTIN = "certin"


class Treatment(str, Enum):
    MITIGATE = "mitigate"
    ACCEPT = "accept"
    TRANSFER = "transfer"
    AVOID = "avoid"


class RiskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    ACCEPTED = "accepted"


class RiskBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# ── Platform (SRS 2.2 / 8.4) ──────────────────────────────────────────────────
class Role(str, Enum):
    ADMIN = "admin"          # Platform Admin
    DPO = "dpo"              # Privacy Officer / DPO
    OWNER = "owner"          # Application Owner (per application)
    AUDITOR = "auditor"      # Auditor (read-only)
    OPERATOR = "operator"    # Scan Operator (per application)


# ── Shared SAEnum instances ───────────────────────────────────────────────────
# One instance per PG type name, reused across every column that uses it, so the
# metadata declares each ENUM type exactly once (no duplicate CREATE TYPE).
environment_enum = pg_enum(Environment, "environment")
hosting_enum = pg_enum(Hosting, "hosting")
user_base_enum = pg_enum(UserBase, "user_base")
lifecycle_enum = pg_enum(Lifecycle, "lifecycle")
data_source_kind_enum = pg_enum(DataSourceKind, "data_source_kind")
detector_pack_source_enum = pg_enum(DetectorPackSource, "detector_pack_source")
scan_state_enum = pg_enum(ScanState, "scan_state")
scan_unit_kind_enum = pg_enum(ScanUnitKind, "scan_unit_kind")
scan_profile_enum = pg_enum(ScanProfile, "scan_profile")
tier_enum = pg_enum(Tier, "tier")
category_enum = pg_enum(Category, "pii_category")
protection_state_enum = pg_enum(ProtectionState, "protection_state")
review_state_enum = pg_enum(ReviewState, "review_state")
dpia_state_enum = pg_enum(DpiaState, "dpia_state")
answer_enum = pg_enum(Answer, "answer")
framework_enum = pg_enum(Framework, "framework")
treatment_enum = pg_enum(Treatment, "treatment")
risk_status_enum = pg_enum(RiskStatus, "risk_status")
risk_band_enum = pg_enum(RiskBand, "risk_band")
role_enum = pg_enum(Role, "role")
