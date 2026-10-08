"""Assessment group (SRS 8.3): questionnaire templates, DPIA assessments,
responses, comments, controls, risks, transitions.

Note on RLS: SRS 8.5 mandates row-level security on the ``dpia_*`` tables keyed on
application. The child tables (responses, comments, risks, transitions) reference a
DPIA, not an application, so each carries a denormalised ``application_id`` (set from
the parent DPIA at insert). That lets the ONE application-keyed RLS policy apply
uniformly and without a per-row subquery — the point of 8.5 is that a bug in the API
filter still cannot leak another application's rows, and a subquery back through an
RLS-protected parent is exactly the fragile path to avoid.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from platform_db import enums
from platform_db.base import Base, TimestampMixin, UUIDPKMixin


class QuestionnaireTemplate(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "questionnaire_templates"
    __table_args__ = (UniqueConstraint("version", name="uq_questionnaire_templates_version"),)

    version: Mapped[str] = mapped_column(String(50), nullable=False)
    sections: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Control(UUIDPKMixin, TimestampMixin, Base):
    """DPDP Act 2023 control library (SRS 5.1). Global reference data — not RLS'd."""

    __tablename__ = "controls"
    __table_args__ = (
        UniqueConstraint("framework", "reference", name="uq_controls_framework_reference"),
    )

    framework: Mapped[enums.Framework] = mapped_column(enums.framework_enum, nullable=False)
    reference: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_keys: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}")


class DpiaAssessment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "dpia_assessments"
    __table_args__ = (Index("ix_dpia_assessments_application_id", "application_id"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[enums.DpiaState] = mapped_column(
        enums.dpia_state_enum, nullable=False, default=enums.DpiaState.DRAFT)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Snapshot of the inventory at creation keeps the assessment stable while scans
    # continue (SRS 8.3).
    inventory_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}")
    inherent_score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    residual_score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    risk_band: Mapped[enums.RiskBand | None] = mapped_column(
        enums.risk_band_enum, nullable=True)
    submitted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)


class QuestionnaireResponse(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "questionnaire_responses"
    __table_args__ = (
        UniqueConstraint("dpia_id", "question_key",
                         name="uq_questionnaire_responses_dpia_id_question_key"),
        Index("ix_questionnaire_responses_application_id", "application_id"),
    )

    dpia_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dpia_assessments.id", ondelete="CASCADE"),
        nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    question_key: Mapped[str] = mapped_column(String(50), nullable=False)
    answer: Mapped[enums.Answer] = mapped_column(enums.answer_enum, nullable=False)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict,
                                                server_default="{}")
    answered_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    answered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DpiaComment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "dpia_comments"
    __table_args__ = (Index("ix_dpia_comments_application_id", "application_id"),)

    dpia_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dpia_assessments.id", ondelete="CASCADE"),
        nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    question_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Risk(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint("likelihood BETWEEN 1 AND 5", name="likelihood_range"),
        CheckConstraint("impact BETWEEN 1 AND 5", name="impact_range"),
        Index("ix_risks_application_id", "application_id"),
    )

    dpia_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dpia_assessments.id", ondelete="CASCADE"),
        nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("controls.id", ondelete="SET NULL"), nullable=True)
    likelihood: Mapped[int] = mapped_column(Integer, nullable=False)
    impact: Mapped[int] = mapped_column(Integer, nullable=False)
    inherent_score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    treatment: Mapped[enums.Treatment | None] = mapped_column(
        enums.treatment_enum, nullable=True)
    treatment_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[enums.RiskStatus] = mapped_column(
        enums.risk_status_enum, nullable=False, default=enums.RiskStatus.OPEN)
    residual_likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_impact: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DpiaTransition(UUIDPKMixin, Base):
    """Workflow history (SRS 8.3). Immutable records, so no update quartet — just the
    moment and the actor. Carries ``application_id`` for the uniform RLS policy."""

    __tablename__ = "dpia_transitions"
    __table_args__ = (Index("ix_dpia_transitions_application_id", "application_id"),)

    dpia_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("dpia_assessments.id", ondelete="CASCADE"),
        nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False)
    from_state: Mapped[enums.DpiaState | None] = mapped_column(
        enums.dpia_state_enum, nullable=True)
    to_state: Mapped[enums.DpiaState] = mapped_column(enums.dpia_state_enum, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
