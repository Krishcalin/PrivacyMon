"""Continuous monitoring: change_events table (SRS FR-4.x).

Records a material inventory change detected between two scans, application-scoped and
RLS-isolated. Idempotent like 0002: a fresh database already has the table + its policy
from the baseline's create_all (the model is in the metadata and the table is in
``ddl.RLS_TABLES``); an older database gets it here. Offline (--sql) is a no-op.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

from platform_db import ddl
from platform_db.models.scanning import ChangeEvent

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return  # the baseline already emits change_events + its policy in offline SQL
    bind = op.get_bind()
    if "change_events" in sa.inspect(bind).get_table_names():
        return  # fresh DB: the baseline's create_all + rls_up already made it
    ChangeEvent.__table__.create(bind=bind, checkfirst=False)
    for statement in ddl.rls_up_table("change_events", "application_id"):
        op.execute(statement)


def downgrade() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    if "change_events" not in sa.inspect(bind).get_table_names():
        return
    for statement in ddl.rls_down_table("change_events"):
        op.execute(statement)
    ChangeEvent.__table__.drop(bind=bind, checkfirst=False)
