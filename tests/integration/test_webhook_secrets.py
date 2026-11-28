"""S20 (D-082): the webhook secret writer and reader, on real Postgres.

Positive control: a secret written by the writer is read back by the publisher's reader.
Negative controls: the stored bytes do not contain the secret; without a key no secret is returned
(the publisher then keeps the event, it never sends an unsigned delivery); a third secret retires
the oldest one (two secrets stay active).
"""

import importlib
from types import ModuleType

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.api_support import seed_tenant

pytestmark = [pytest.mark.integration]

KEY = bytes(range(32))


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def test_secret_is_stored_sealed_and_read_back(pg_url: str) -> None:
    engine = create_async_engine(pg_url)
    try:
        await seed_tenant(engine, "tenant-secret-a")
        writer = _mod("transcribe_engine.infrastructure.db.outbox")
        secret = await writer.add_webhook_secret(engine, KEY, "tenant-secret-a")
        async with engine.connect() as conn:
            await conn.execute(text("SELECT set_config('app.system','on',true)"))
            raw = (
                (
                    await conn.execute(
                        text(
                            "SELECT secret FROM webhook_secrets WHERE tenant_id = 'tenant-secret-a'"
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert raw
        for stored in raw:
            assert secret.encode() not in bytes(stored)
        reader = writer.SqlWebhookSecrets(engine, key=KEY)
        assert secret.encode() in await reader.active_secrets("tenant-secret-a")
    finally:
        await engine.dispose()


async def test_no_key_means_no_secrets(pg_url: str) -> None:
    engine = create_async_engine(pg_url)
    try:
        await seed_tenant(engine, "tenant-secret-b")
        writer = _mod("transcribe_engine.infrastructure.db.outbox")
        await writer.add_webhook_secret(engine, KEY, "tenant-secret-b")
        keyless = writer.SqlWebhookSecrets(engine, key=None)
        assert await keyless.active_secrets("tenant-secret-b") == ()
    finally:
        await engine.dispose()


async def test_third_secret_retires_the_oldest(pg_url: str) -> None:
    engine = create_async_engine(pg_url)
    try:
        await seed_tenant(engine, "tenant-secret-c")
        writer = _mod("transcribe_engine.infrastructure.db.outbox")
        first = await writer.add_webhook_secret(engine, KEY, "tenant-secret-c")
        await writer.add_webhook_secret(engine, KEY, "tenant-secret-c")
        third = await writer.add_webhook_secret(engine, KEY, "tenant-secret-c")
        active = await writer.SqlWebhookSecrets(engine, key=KEY).active_secrets("tenant-secret-c")
        assert len(active) == 2
        assert first.encode() not in active
        assert third.encode() in active
    finally:
        await engine.dispose()
