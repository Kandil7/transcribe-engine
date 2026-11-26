"""S10: the result of a completed job is its stored transcript (words and warnings).

Runs against Postgres and MinIO (Testcontainers). The API is the real app; the transcript is written
through the unit of work, as ProcessJob does.
"""

import importlib
from types import ModuleType

import pytest

from tests.integration.api_support import (
    auth,
    build_client,
    create_job,
    force_state,
    issue_key,
    new_tenant,
    seed_tenant,
    storage_for,
    upload,
)
from transcribe_engine.infrastructure.db.session import make_engine

pytestmark = [pytest.mark.integration]

PAYLOAD = b"RIFF" + b"\x00" * 64


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def test_completed_job_returns_its_stored_words(minio: object, app_url: str) -> None:
    """Positive control for the result endpoint: 200 with the stored words in order."""
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    key = await issue_key(engine, tenant, ["transcribe:write", "transcribe:read"])
    merge = _mod("transcribe_engine.domain.merge")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    merged = merge.MergedWords(
        words=(merge.Word("عايز", 0, 500, None, 0), merge.Word("أروح", 500, 900, None, 1)),
        sample_rate=16_000,
    )
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, key, PAYLOAD)
        job_id = (await create_job(client, key, upload_id)).json()["id"]
        await force_state(engine, job_id, "COMPLETED")
        async with uow_mod.SqlUnitOfWork(engine, tenant_id=tenant) as uow:
            await uow.chunks.save_transcript(tenant, job_id, merged)
            await uow.commit()
        result = await client.get(
            f"/v1/transcriptions/{job_id}/result?format=json", headers=auth(key)
        )
    assert result.status_code == 200
    body = result.json()
    assert [w["text"] for w in body["words"]] == ["عايز", "أروح"]
    assert body["words"][0]["start_ms"] == 0
    assert body["words"][1]["chunk_idx"] == 1
    await engine.dispose()


async def test_completed_job_without_a_transcript_is_404(minio: object, app_url: str) -> None:
    """A completed job with no stored transcript has no result: 404, never an empty 200."""
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    key = await issue_key(engine, tenant, ["transcribe:write", "transcribe:read"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, key, PAYLOAD)
        job_id = (await create_job(client, key, upload_id)).json()["id"]
        await force_state(engine, job_id, "COMPLETED")
        result = await client.get(
            f"/v1/transcriptions/{job_id}/result?format=json", headers=auth(key)
        )
    assert result.status_code == 404
    await engine.dispose()
