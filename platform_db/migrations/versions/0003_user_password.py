"""Local-auth password hash on users (SRS 11.1).

Idempotent like 0002: a fresh database already has the column from the baseline's
create_all (the model carries it); an older database gets it added here.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    return "password_hash" in cols


def upgrade() -> None:
    if context.is_offline_mode():
        return
    if not _has_column():
        op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    if context.is_offline_mode():
        return
    if _has_column():
        op.drop_column("users", "password_hash")
