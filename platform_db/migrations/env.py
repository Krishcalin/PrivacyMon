"""Alembic environment for the platform database.

Migrations run with a SYNCHRONOUS psycopg 3 engine even though the app uses the
async driver — Alembic is a one-shot admin task and sync keeps env.py simple. The
URL comes from ``PRIVACYMON_DB_URL`` (falling back to the non-secret dev value in
alembic.ini) so no credential is committed.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the repo root importable so `platform_db` resolves when alembic runs.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_db import Base  # noqa: E402  (after sys.path shim)

config = context.config

_env_url = os.getenv("PRIVACYMON_DB_URL")
if _env_url:
    # psycopg 3 sync driver for migrations.
    if _env_url.startswith("postgresql://"):
        _env_url = "postgresql+psycopg://" + _env_url[len("postgresql://"):]
    config.set_main_option("sqlalchemy.url", _env_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
