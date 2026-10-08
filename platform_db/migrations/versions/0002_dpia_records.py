"""DPIA processing records: the 30-field per-application DPDP sheet (dpia_records).

Idempotent across the two paths that exist because the baseline uses create_all:
 * fresh database — the baseline's ``Base.metadata.create_all`` already made the table
   (the model is in the metadata) and RLS applied to it (``dpia_records`` is now in
   ``ddl.RLS_TABLES``), so this migration skips;
 * database migrated before this table existed — it creates the table and its RLS.
Offline (``--sql``) is also a no-op here, because the baseline SQL already emits the
table and its policy from the metadata.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from platform_db import ddl
from platform_db.models.assessment import DpiaRecord

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return  # the baseline already emits dpia_records + its policy in offline SQL
    bind = op.get_bind()
    if "dpia_records" in sa.inspect(bind).get_table_names():
        return  # fresh DB: the baseline's create_all + rls_up already made it
    DpiaRecord.__table__.create(bind=bind, checkfirst=False)
    for statement in ddl.rls_up_table("dpia_records", "application_id"):
        op.execute(statement)


def downgrade() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    if "dpia_records" not in sa.inspect(bind).get_table_names():
        return
    for statement in ddl.rls_down_table("dpia_records"):
        op.execute(statement)
    DpiaRecord.__table__.drop(bind=bind, checkfirst=False)
