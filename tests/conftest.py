"""Shared fixtures for the integration and contract suites."""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from tests.integration.test_migrations import _alembic_config


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """A migrated Postgres. The URL is asyncpg-qualified for SQLAlchemy."""
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        dsn = "postgresql+asyncpg://" + pg.get_connection_url().split("://", 1)[1]
        previous = os.environ.get("TE_DATABASE_URL")
        os.environ["TE_DATABASE_URL"] = dsn
        try:
            command.upgrade(_alembic_config(), "head")
            yield dsn
        finally:
            if previous is None:
                os.environ.pop("TE_DATABASE_URL", None)
            else:
                os.environ["TE_DATABASE_URL"] = previous
