"""AC-4: the migration chain upgrades, downgrades and upgrades again on a real Postgres."""

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
HEAD = "0007_webhooks_outbox"  # D-049: moved from 0006 when S20 added webhook columns


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


async def _applied_revisions(dsn: str) -> list[str]:
    conn = await asyncpg.connect(dsn)
    try:
        exists = await conn.fetchval("select to_regclass('public.alembic_version') is not null")
        if not exists:
            return []
        rows = await conn.fetch("select version_num from alembic_version order by version_num")
        return [str(row["version_num"]) for row in rows]
    finally:
        await conn.close()


def test_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        # Testcontainers returns a driver-qualified URL; asyncpg needs the plain postgresql:// DSN.
        dsn = "postgresql://" + pg.get_connection_url().split("://", 1)[1]
        monkeypatch.setenv(
            "TE_DATABASE_URL", dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
        )
        cfg = _alembic_config()

        command.upgrade(cfg, "head")
        assert asyncio.run(_applied_revisions(dsn)) == [HEAD]

        command.downgrade(cfg, "base")
        assert asyncio.run(_applied_revisions(dsn)) == []

        command.upgrade(cfg, "head")
        assert asyncio.run(_applied_revisions(dsn)) == [HEAD]
