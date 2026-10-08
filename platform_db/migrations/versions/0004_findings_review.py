"""Findings review workflow + editable inventory (retention) support.

Adds the small columns the review/suppress/inventory-edit features need:
  - ``inventory.retention`` — owner-annotated retention period (preserved across scans)
  - ``suppressions.created_by`` — who created a suppression (SRS 8.2 audit story)

Idempotent like 0002/0003: a fresh database already has these from the baseline's
create_all (the models carry them); an older database gets them added here.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if context.is_offline_mode():
        return
    if "retention" not in _columns("inventory"):
        op.add_column("inventory", sa.Column("retention", sa.Text(), nullable=True))
    if "created_by" not in _columns("suppressions"):
        op.add_column(
            "suppressions",
            sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    if context.is_offline_mode():
        return
    if "created_by" in _columns("suppressions"):
        op.drop_column("suppressions", "created_by")
    if "retention" in _columns("inventory"):
        op.drop_column("inventory", "retention")
