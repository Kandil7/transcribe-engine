"""S18 AC-7 and AC-8 (integration, Postgres and MinIO, through the API with the RLS-enforced role).

AC-8: a search hit carries the job's media id, the start and end in milliseconds, and a player deep
link with the start in seconds. The assertions are exact, so `?t=5` cannot match `?t=5000`.
AC-7: a second tenant's key finds nothing for the first tenant's words, and cannot read the first
tenant's chunks (404, not the chunks).

Positive controls: the owning tenant finds the word. Negative control: a word that was never said
returns no hits. Without an embedder the search routes answer 503.
"""

import importlib
from types import ModuleType

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes.embedder import FakeEmbedder
from tests.integration.api_support import (
    auth,
    force_state,
    issue_key,
    new_tenant,
    seed_tenant,
    storage_for,
    upload,
)
from transcribe_engine.infrastructure.db.session import make_engine

pytestmark = [pytest.mark.integration, pytest.mark.contract]
PAYLOAD = b"RIFF" + b"\x00" * 64


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def _completed_job(
    client: httpx.AsyncClient, engine: AsyncEngine, tenant: str, key: str, words: list[str]
) -> tuple[str, str]:
    """A completed job whose transcript is `words`, one segment from 5 000 ms.

    Returns (job id, media id)."""
    merge = _mod("transcribe_engine.domain.merge")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    upload_id = await upload(client, key, PAYLOAD)
    created = await client.post(
        "/v1/transcriptions",
        headers=auth(key),
        json={"upload_id": upload_id, "language": "ar", "diarization": False},
    )
    job_id = created.json()["id"]
    await force_state(engine, job_id, "COMPLETED")
    merged = merge.MergedWords(
        words=tuple(
            merge.Word(w, 5_000 + i * 400, 5_000 + i * 400 + 350, None, 0)
            for i, w in enumerate(words)
        ),
        sample_rate=16_000,
    )
    async with uow_mod.SqlUnitOfWork(engine, tenant_id=tenant) as uow:
        await uow.chunks.save_transcript(tenant, job_id, merged)
        await uow.commit()
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
        media_id = (
            await conn.execute(text("SELECT media_id FROM jobs WHERE id = :j"), {"j": job_id})
        ).scalar_one()
    return job_id, media_id


async def test_hit_carries_media_span_and_deeplink(app_url: str, minio: object) -> None:
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    key = await issue_key(engine, tenant, ["transcribe:write", "transcribe:read"])
    app = _mod("transcribe_engine.main").build_app(
        engine=engine, storage=storage_for(minio), embedder=FakeEmbedder()
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            words = ["alpha", "beta", "gamma", "delta"] * 5
            job_id, media_id = await _completed_job(client, engine, tenant, key, words)
            indexed = await client.post(f"/v1/transcriptions/{job_id}:index", headers=auth(key))
            assert indexed.status_code == 202

            hits = (await client.get("/v1/search", params={"q": "beta"}, headers=auth(key))).json()[
                "hits"
            ]
            assert hits, "the indexed word must be found (positive control)"
            hit = hits[0]
            assert hit["job_id"] == job_id
            assert hit["media_id"] == media_id
            assert hit["start_ms"] == 5_000
            assert hit["end_ms"] == 5_000 + 19 * 400 + 350
            assert hit["deeplink"] == f"/media/{media_id}?t=5"

            none = (
                await client.get("/v1/search", params={"q": "zzznever"}, headers=auth(key))
            ).json()["hits"]
            assert none == []
    finally:
        await engine.dispose()


async def test_another_tenant_sees_nothing_through_the_api(app_url: str, minio: object) -> None:
    owner, other = new_tenant(), new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, owner)
    await seed_tenant(engine, other)
    owner_key = await issue_key(engine, owner, ["transcribe:write", "transcribe:read"])
    other_key = await issue_key(engine, other, ["transcribe:read"])
    app = _mod("transcribe_engine.main").build_app(
        engine=engine, storage=storage_for(minio), embedder=FakeEmbedder()
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            job_id, _ = await _completed_job(
                client, engine, owner, owner_key, ["secretword", "beta", "gamma"]
            )
            await client.post(f"/v1/transcriptions/{job_id}:index", headers=auth(owner_key))

            own = (
                await client.get("/v1/search", params={"q": "secretword"}, headers=auth(owner_key))
            ).json()["hits"]
            assert own, "the owner finds its own word (positive control)"

            foreign = (
                await client.get("/v1/search", params={"q": "secretword"}, headers=auth(other_key))
            ).json()["hits"]
            assert foreign == []

            chunks = await client.get(
                f"/v1/transcriptions/{job_id}/rag-chunks", headers=auth(other_key)
            )
            assert chunks.status_code == 404
    finally:
        await engine.dispose()


async def test_search_answers_503_without_an_embedder(app_url: str, minio: object) -> None:
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    key = await issue_key(engine, tenant, ["transcribe:read"])
    app = _mod("transcribe_engine.main").build_app(engine=engine, storage=storage_for(minio))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/v1/search", params={"q": "beta"}, headers=auth(key))
            assert response.status_code == 503
            assert response.json()["code"] == "search_unavailable"
    finally:
        await engine.dispose()
