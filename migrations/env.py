"""Alembic environment: async engine, URL from `TE_DATABASE_URL` via Settings.

`target_metadata` is the Core metadata from infrastructure/db/models.py (S05); autogenerate compares
against it. Migrations are written by hand or with `alembic revision --autogenerate` and reviewed.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from transcribe_engine.infrastructure.db.models import metadata
from transcribe_engine.infrastructure.settings import Settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = metadata  # S05: autogenerate compares against the ORM Core tables


def _database_url() -> str:
    return Settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations_on(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": _database_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations_on)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against the database through an async engine."""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
