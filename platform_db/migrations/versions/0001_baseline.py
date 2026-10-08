"""Baseline schema: SRS section 8 registry/scanning/assessment/platform tables,
plus row-level security (8.5) and the append-only audit-log trigger (8.4).

The tables, native ENUM types, indexes, the ``findings`` LIST partition parent and
the GIN indexes all come from ``Base.metadata`` so the migration can never drift from
the models. The things ``create_all`` does not express — RLS policies and the audit
trigger — are applied explicitly from ``platform_db.ddl``.

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""
from __future__ import annotations

from alembic import op

from platform_db import Base, ddl

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=False)
    for statement in ddl.audit_trigger_up() + ddl.rls_up():
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    for statement in ddl.rls_down() + ddl.audit_trigger_down():
        op.execute(statement)
    Base.metadata.drop_all(bind=bind, checkfirst=False)
