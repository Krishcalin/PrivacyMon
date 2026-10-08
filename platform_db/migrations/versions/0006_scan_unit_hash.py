"""Incremental scans: scan_units.content_hash change marker.

Idempotent like 0003/0004: a fresh database already has the column from the baseline's
create_all; an older database gets it added here. Offline (--sql) is a no-op.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if context.is_offline_mode():
        return
    if not _has_column("scan_units", "content_hash"):
        op.add_column("scan_units", sa.Column("content_hash", sa.String(64), nullable=True))
    if not _has_column("scan_jobs", "incremental"):
        op.add_column("scan_jobs", sa.Column(
            "incremental", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    if context.is_offline_mode():
        return
    if _has_column("scan_jobs", "incremental"):
        op.drop_column("scan_jobs", "incremental")
    if _has_column("scan_units", "content_hash"):
        op.drop_column("scan_units", "content_hash")
