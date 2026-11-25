"""Shared fixtures for the integration and contract suites.

Two migrated databases share one Postgres container:
- `pg_url`: the database for repository, queue and chaos suites (owner role; RLS bypassed).
- `app_url`: a separate database for the API suite, reached through a role that cannot bypass RLS.
Keeping them apart stops API jobs from being claimed by the queue tests.
"""

import asyncio
import os
import re
from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.minio import MinioContainer

from tests.integration.test_migrations import _alembic_config

MINIO_IMAGE = "cgr.dev/chainguard/minio:latest"  # D-002
API_DB = "te_api"


def _migrate(dsn: str) -> None:
    previous = os.environ.get("TE_DATABASE_URL")
    os.environ["TE_DATABASE_URL"] = dsn
    try:
        command.upgrade(_alembic_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("TE_DATABASE_URL", None)
        else:
            os.environ["TE_DATABASE_URL"] = previous


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_url(pg_container: PostgresContainer) -> str:
    """The migrated default database for the queue, repository and chaos suites."""
    dsn = "postgresql+asyncpg://" + pg_container.get_connection_url().split("://", 1)[1]
    _migrate(dsn)
    return dsn


@pytest.fixture(scope="session")
def app_url(pg_url: str, pg_container: PostgresContainer) -> str:
    """A separate migrated database for the API suite, reached as a role that cannot bypass RLS.

    Superusers bypass row-level security, so the RLS tests need this role. Production must use a
    NOBYPASSRLS role too (D-024). The role and its grants are test-only.
    """

    async def _create_db() -> None:
        engine = create_async_engine(pg_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                exists = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": API_DB}
                )
                if exists.first() is None:
                    await conn.execute(text(f'CREATE DATABASE "{API_DB}"'))
        finally:
            await engine.dispose()

    async def _grant(dsn: str) -> None:
        engine = create_async_engine(dsn)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'te_app') "
                        "THEN CREATE ROLE te_app LOGIN PASSWORD 'te_app' "
                        "NOSUPERUSER NOBYPASSRLS; END IF; END $$"
                    )
                )
                await conn.execute(text("GRANT USAGE ON SCHEMA public TO te_app"))
                await conn.execute(
                    text(
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                        "TO te_app"
                    )
                )
                await conn.execute(
                    text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO te_app")
                )
        finally:
            await engine.dispose()

    asyncio.run(_create_db())
    api_dsn = re.sub(r"/[^/]+$", f"/{API_DB}", pg_url)
    _migrate(api_dsn)
    asyncio.run(_grant(api_dsn))
    return re.sub(r"://[^@]+@", "://te_app:te_app@", api_dsn, count=1)


@pytest.fixture(scope="session")
def minio() -> Iterator[MinioContainer]:
    container = MinioContainer(MINIO_IMAGE).with_env(
        "MINIO_KMS_SECRET_KEY", "local-test:MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )
    with container:
        yield container
