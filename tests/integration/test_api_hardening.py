"""S08 hardening tests added after review: positive controls, races, RLS, body binding.

Each refusal is paired with the same request succeeding, so an always-erroring route fails.
"""

import asyncio

import pytest
from sqlalchemy import text

from tests.integration.api_support import (
    auth,
    build_client,
    create_job,
    issue_key,
    new_tenant,
    seed_tenant,
    storage_for,
    upload,
)
from transcribe_engine.infrastructure.db.session import make_engine

pytestmark = [pytest.mark.integration]

PAYLOAD = b"RIFF" + b"\x00" * 64


async def test_missing_upload_is_404_and_a_real_upload_is_202(minio: object, app_url: str) -> None:
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    write = await issue_key(engine, tenant, ["transcribe:write"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        good = await upload(client, write, PAYLOAD)
        ok = await create_job(client, write, good)
        missing = await create_job(client, write, "0" * 32)
    assert ok.status_code == 202
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
    await engine.dispose()


async def test_unsupported_language_is_422_and_arabic_is_202(minio: object, app_url: str) -> None:
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    write = await issue_key(engine, tenant, ["transcribe:write"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        ok = await create_job(client, write, upload_id)
        english = await create_job(client, write, upload_id, language="en")
    assert ok.status_code == 202
    assert english.status_code == 422
    await engine.dispose()


async def test_concurrent_creates_never_exceed_the_limit(minio: object, app_url: str) -> None:
    """Three creates race for a limit of two: exactly two are accepted."""
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant, max_active_jobs=2)
    write = await issue_key(engine, tenant, ["transcribe:write"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        ids = [await upload(client, write, PAYLOAD + bytes([i])) for i in range(3)]
        responses = await asyncio.gather(*(create_job(client, write, i) for i in ids))
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [202, 202, 429]
    await engine.dispose()


async def test_same_key_with_a_different_body_is_422(minio: object, app_url: str) -> None:
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    write = await issue_key(engine, tenant, ["transcribe:write"])
    headers = {**auth(write), "Idempotency-Key": "reused-key"}
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        first_id = await upload(client, write, PAYLOAD)
        second_id = await upload(client, write, PAYLOAD + b"x")
        body = {"upload_id": first_id, "language": "ar", "diarization": False}
        first = await client.post("/v1/transcriptions", json=body, headers=headers)
        other = {"upload_id": second_id, "language": "ar", "diarization": False}
        second = await client.post("/v1/transcriptions", json=other, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 422
    await engine.dispose()


async def test_rls_isolates_tenants_on_a_raw_session(minio: object, app_url: str) -> None:
    """Tenant B's setting shows none of tenant A's jobs, even with the job id in hand."""
    tenant_a = new_tenant()
    tenant_b = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant_a)
    await seed_tenant(engine, tenant_b)
    write = await issue_key(engine, tenant_a, ["transcribe:write"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        job_id = (await create_job(client, write, upload_id)).json()["id"]
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_b})
        seen = await conn.execute(text("SELECT count(*) FROM jobs WHERE id = :id"), {"id": job_id})
        assert seen.scalar_one() == 0
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
        seen = await conn.execute(text("SELECT count(*) FROM jobs WHERE id = :id"), {"id": job_id})
        assert seen.scalar_one() == 1
    await engine.dispose()


async def test_cancel_a_pending_job_is_202(minio: object, app_url: str) -> None:
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    write = await issue_key(engine, tenant, ["transcribe:write", "transcribe:read"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        job_id = (await create_job(client, write, upload_id)).json()["id"]
        cancelled = await client.post(f"/v1/transcriptions/{job_id}:cancel", headers=auth(write))
        again = await client.post(f"/v1/transcriptions/{job_id}:cancel", headers=auth(write))
    assert cancelled.status_code == 202, cancelled.text
    assert cancelled.json()["state"] == "CANCELLED"
    assert again.status_code == 409
    await engine.dispose()


async def test_retry_after_is_an_integer_and_absent_when_terminal(
    minio: object, app_url: str
) -> None:
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    write = await issue_key(engine, tenant, ["transcribe:write", "transcribe:read"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        job_id = (await create_job(client, write, upload_id)).json()["id"]
        pending = await client.get(f"/v1/transcriptions/{job_id}", headers=auth(write))
        await client.post(f"/v1/transcriptions/{job_id}:cancel", headers=auth(write))
        done = await client.get(f"/v1/transcriptions/{job_id}", headers=auth(write))
    assert int(pending.headers["retry-after"]) > 0
    assert "retry-after" not in done.headers
    await engine.dispose()
