"""Contract of the ArtifactStore port (S19): one suite, run against the fake and the Postgres
adapter.

Every check has a positive control (the stored artifact is read back exactly), so a store that
returns nothing cannot pass. The Postgres run uses the RLS-enforced role (app_url).
"""

import contextlib
import importlib
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import pytest

from tests.fakes.artifacts import FakeArtifactStore

pytestmark = [pytest.mark.contract]


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _artifact(
    version: int = 1, model_version: str = "1", payload: dict[str, object] | None = None
) -> Any:
    domain = _mod("transcribe_engine.domain.artifacts")
    return domain.Artifact(
        transcript_id="job-art",
        transcript_version=version,
        kind="chapters",
        model="rule-chapters",
        model_version=model_version,
        payload=payload if payload is not None else {"chapters": [{"title": "أول", "start_ms": 0}]},
    )


@dataclass(frozen=True)
class Env:
    kind: str
    app_url: str | None = None


@pytest.fixture(params=["fake", pytest.param("sql", marks=pytest.mark.integration)])
def env(request: pytest.FixtureRequest) -> Env:
    """Resolved before the event loop starts (the Postgres fixture runs migrations)."""
    if request.param == "fake":
        return Env(kind="fake")
    return Env(kind="sql", app_url=request.getfixturevalue("app_url"))


@contextlib.asynccontextmanager
async def _open(env: Env) -> AsyncGenerator[tuple[Any, str], None]:
    """Yields (store, tenant) for one fresh tenant."""
    tenant = f"tenant-{uuid.uuid4().hex[:8]}"
    if env.kind == "fake":
        yield FakeArtifactStore(), tenant
        return
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415 - Docker-only path

    from tests.integration.api_support import seed_tenant  # noqa: PLC0415

    engine = create_async_engine(str(env.app_url))
    await seed_tenant(engine, tenant)
    store = _mod("transcribe_engine.infrastructure.db.artifacts").SqlArtifactStore(engine)
    try:
        yield store, tenant
    finally:
        await engine.dispose()


async def test_a_stored_artifact_reads_back_exactly(env: Env) -> None:
    """Positive control: the payload, with nested lists and non-ASCII text, comes back equal."""
    async with _open(env) as (store, tenant):
        original = _artifact()
        await store.put(tenant, original)
        found = await store.get(tenant, "job-art", 1, "chapters", "rule-chapters", "1")
        assert found == original


async def test_other_version_model_or_tenant_finds_nothing(env: Env) -> None:
    """Negative controls: another transcript version, another model version, or another tenant
    gets no row. Positive control: the exact key finds it."""
    async with _open(env) as (store, tenant):
        await store.put(tenant, _artifact(version=1))
        assert await store.get(tenant, "job-art", 1, "chapters", "rule-chapters", "1") is not None
        assert await store.get(tenant, "job-art", 2, "chapters", "rule-chapters", "1") is None
        assert await store.get(tenant, "job-art", 1, "chapters", "rule-chapters", "2") is None
        assert (
            await store.get("tenant-other-x", "job-art", 1, "chapters", "rule-chapters", "1")
            is None
        )


async def test_a_second_put_replaces_the_payload(env: Env) -> None:
    """A retried derivation writes the same key again; the row holds the new payload."""
    async with _open(env) as (store, tenant):
        await store.put(tenant, _artifact(payload={"chapters": []}))
        await store.put(tenant, _artifact(payload={"chapters": [{"title": "new", "start_ms": 0}]}))
        found = await store.get(tenant, "job-art", 1, "chapters", "rule-chapters", "1")
        assert found is not None
        assert found.payload == {"chapters": [{"title": "new", "start_ms": 0}]}
