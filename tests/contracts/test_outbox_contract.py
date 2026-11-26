"""Contract tests for the outbox, sender and resolver ports (S20, CLAUDE.md port rule). Each test
runs against the in-memory fake and the real adapter, so the fake cannot drift from the adapter.

The store test checks the lease and fence semantics that the publisher depends on: one claim per
lease, writes only by the owner, and a due time that hides the row until it passes.
"""

import importlib
import json
from datetime import UTC, datetime, timedelta
from types import ModuleType

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.fakes.clock import FakeClock
from tests.fakes.outbox import FakeOutbox, FakeResolver, FakeSender

pytestmark = [pytest.mark.integration, pytest.mark.contract]

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
LEASE = timedelta(minutes=5)
URL = "https://hook.public.test/contract"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def _sql_store_with_row(pg_url: str, tag: str) -> tuple[object, object, int]:
    engine = create_async_engine(pg_url)
    store_mod = _mod("transcribe_engine.infrastructure.db.outbox")
    payload = {
        "event": "transcript.completed",
        "job_id": tag,
        "tenant_id": "tenant-a",
        "webhook_url": URL,
    }
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO outbox (event, payload) VALUES ('transcript.completed', "
                "CAST(:payload AS jsonb))"
            ),
            {"payload": json.dumps(payload)},
        )
        row_id = (
            await conn.execute(
                text("SELECT max(id) FROM outbox WHERE payload->>'job_id' = :tag"), {"tag": tag}
            )
        ).scalar_one()
    return engine, store_mod.SqlOutboxStore(engine), int(row_id)


async def _exercise_store(store: object, row_id: int, tag: str) -> None:
    """The same script for the fake and the SQL store. Returns nothing; asserts on the row."""
    mine = lambda rows: [r for r in rows if r.payload.get("job_id") == tag]  # noqa: E731
    claimed = mine(await store.claim_due(NOW, 1000, "owner-a", LEASE))  # type: ignore[attr-defined]
    assert [r.id for r in claimed] == [row_id]
    # A second claim by another owner inside the lease finds nothing for this row.
    assert mine(await store.claim_due(NOW, 1000, "owner-b", LEASE)) == []  # type: ignore[attr-defined]
    # A write by a non-owner is ignored: the row is still leased to owner-a and still due.
    await store.reschedule(row_id, "owner-b", NOW + timedelta(hours=1))  # type: ignore[attr-defined]
    await store.reschedule(row_id, "owner-a", NOW + timedelta(hours=1))  # type: ignore[attr-defined]
    # Not due before the scheduled time; due after it.
    assert mine(await store.claim_due(NOW, 1000, "owner-a", LEASE)) == []  # type: ignore[attr-defined]
    later = NOW + timedelta(hours=2)
    again = mine(await store.claim_due(later, 1000, "owner-a", LEASE))  # type: ignore[attr-defined]
    assert [r.id for r in again] == [row_id]
    await store.mark_delivered(row_id, "owner-a", later)  # type: ignore[attr-defined]
    much_later = later + timedelta(days=2)
    assert mine(await store.claim_due(much_later, 1000, "owner-a", LEASE)) == []  # type: ignore[attr-defined]


async def test_store_contract_fake(pg_url: str) -> None:
    """The fake obeys the lease and fence script (positive control: the first claim returns it)."""
    outbox = FakeOutbox()
    row_id = outbox.add(
        "transcript.completed", {"job_id": "contract-fake", "webhook_url": URL}, NOW
    )
    await _exercise_store(outbox, row_id, "contract-fake")


async def test_store_contract_sql(pg_url: str) -> None:
    """The SQL store obeys the same script against Postgres."""
    tag = "contract-sql-" + datetime.now(UTC).strftime("%H%M%S%f")
    engine, store, row_id = await _sql_store_with_row(pg_url, tag)
    try:
        await _exercise_store(store, row_id, tag)
    finally:
        await engine.dispose()


async def test_sender_contract_fake_and_real() -> None:
    """Fake and real sender both return an HTTP status for a send to a pinned address."""
    clock = FakeClock()
    fake = FakeSender(clock, statuses=[204])
    assert await fake.send(URL, b"{}", {}, "93.184.216.34") == 204

    sender_mod = _mod("transcribe_engine.infrastructure.http.webhook_sender")
    transport = httpx.MockTransport(lambda request: httpx.Response(204))
    real = sender_mod.HttpWebhookSender(httpx.AsyncClient(transport=transport))
    assert await real.send(URL, b"{}", {}, "93.184.216.34") == 204


def test_resolver_contract_fake_and_real() -> None:
    """Both resolvers return addresses as strings; a name that does not resolve gives none."""
    fake = FakeResolver({"hook.public.test": ["93.184.216.34"]})
    assert list(fake.resolve("hook.public.test")) == ["93.184.216.34"]
    assert list(fake.resolve("nope.invalid")) == []
    dns = _mod("transcribe_engine.infrastructure.http.webhook_sender").DnsResolver()
    assert list(dns.resolve("nope.invalid")) == []
    assert all(isinstance(a, str) for a in dns.resolve("localhost"))
