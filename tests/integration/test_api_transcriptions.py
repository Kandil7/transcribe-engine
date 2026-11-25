"""S08 API acceptance tests: create, read, cancel, delete request, result, auth, idempotency.

All tests run against the real app (ASGI), real Postgres and MinIO. Each xfail is removed
in the commit that makes it pass.
"""

import pytest
from sqlalchemy import text

from tests.integration.api_support import (
    auth,
    build_client,
    create_job,
    force_state,
    issue_key,
    seed_tenant,
    storage_for,
    upload,
)
from transcribe_engine.infrastructure.db.session import make_engine

pytestmark = [pytest.mark.integration]

PAYLOAD = b"RIFF" + b"\x00" * 64


@pytest.mark.xfail(strict=True, reason="S08")
async def test_create_returns_202_and_location(minio: object, pg_url: str) -> None:
    """AC-1: upload, then create a job: 202 Accepted with Location to the job."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a")
    write = await issue_key(engine, "tenant-a", ["transcribe:write"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        response = await create_job(client, write, upload_id)
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert response.headers["location"] == f"/v1/transcriptions/{job_id}"
    await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S08")
async def test_other_tenant_gets_404(minio: object, pg_url: str) -> None:
    """AC-2: another tenant's job id is 404 for read, cancel, delete and result (never 403)."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a")
    await seed_tenant(engine, "tenant-b")
    a_write = await issue_key(engine, "tenant-a", ["transcribe:write", "transcribe:read"])
    b_read = await issue_key(engine, "tenant-b", ["transcribe:write", "transcribe:read"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, a_write, PAYLOAD)
        job_id = (await create_job(client, a_write, upload_id)).json()["id"]
        read = await client.get(f"/v1/transcriptions/{job_id}", headers=auth(b_read))
        cancel = await client.post(f"/v1/transcriptions/{job_id}:cancel", headers=auth(b_read))
        delete = await client.delete(f"/v1/transcriptions/{job_id}", headers=auth(b_read))
        result = await client.get(
            f"/v1/transcriptions/{job_id}/result?format=json", headers=auth(b_read)
        )
    assert [read.status_code, cancel.status_code, delete.status_code, result.status_code] == [
        404
    ] * 4
    await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S08")
async def test_rls_is_the_second_layer(minio: object, pg_url: str) -> None:
    """AC-3 (api side): the tenant setting limits a raw query; without it the query sees no jobs."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a")
    write = await issue_key(engine, "tenant-a", ["transcribe:write"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        job_id = (await create_job(client, write, upload_id)).json()["id"]
    async with engine.connect() as conn:
        bare = await conn.execute(text("SELECT count(*) FROM jobs WHERE id = :id"), {"id": job_id})
        assert bare.scalar_one() == 0
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.tenant_id', 'tenant-a', true)"))
        mine = await conn.execute(text("SELECT count(*) FROM jobs WHERE id = :id"), {"id": job_id})
        assert mine.scalar_one() == 1
    await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S08")
async def test_idempotency_key_replays_response(minio: object, pg_url: str) -> None:
    """AC-4: the same Idempotency-Key gives the same job; one job row exists."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a")
    write = await issue_key(engine, "tenant-a", ["transcribe:write"])
    headers = {**auth(write), "Idempotency-Key": "order-42"}
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        body = {"upload_id": upload_id, "language": "ar", "diarization": False}
        first = await client.post("/v1/transcriptions", json=body, headers=headers)
        second = await client.post("/v1/transcriptions", json=body, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.system', 'on', true)"))
        count = await conn.execute(text("SELECT count(*) FROM jobs"))
        assert count.scalar_one() == 1
    await engine.dispose()


async def test_missing_or_bad_key_401(minio: object, pg_url: str) -> None:
    """AC-5: no key and a made-up key are both 401 with problem+json."""
    engine = make_engine(pg_url)
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        missing = await client.post("/v1/uploads")
        bogus = await client.post("/v1/uploads", headers=auth("te_not-a-real-key"))
    assert missing.status_code == 401
    assert bogus.status_code == 401
    assert missing.headers["content-type"].startswith("application/problem+json")
    await engine.dispose()


async def test_wrong_scope_403(minio: object, pg_url: str) -> None:
    """AC-5: a read-only key cannot create uploads (403)."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a")
    read_only = await issue_key(engine, "tenant-a", ["transcribe:read"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        response = await client.post("/v1/uploads", headers=auth(read_only))
    assert response.status_code == 403
    await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S08")
async def test_get_non_terminal_has_retry_after(minio: object, pg_url: str) -> None:
    """AC-6: a non-terminal job reports its state and Retry-After."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a")
    write = await issue_key(engine, "tenant-a", ["transcribe:write", "transcribe:read"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        job_id = (await create_job(client, write, upload_id)).json()["id"]
        response = await client.get(f"/v1/transcriptions/{job_id}", headers=auth(write))
    assert response.status_code == 200
    assert response.json()["state"] == "PENDING_VALIDATION"
    assert "retry-after" in response.headers
    await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S08")
async def test_cancel_terminal_409(minio: object, pg_url: str) -> None:
    """AC-7: cancelling a completed job is 409 Conflict."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a")
    write = await issue_key(engine, "tenant-a", ["transcribe:write", "transcribe:read"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        job_id = (await create_job(client, write, upload_id)).json()["id"]
        await force_state(engine, job_id, "COMPLETED")
        response = await client.post(f"/v1/transcriptions/{job_id}:cancel", headers=auth(write))
    assert response.status_code == 409
    await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S08")
async def test_concurrency_limit_429(minio: object, pg_url: str) -> None:
    """AC-8: the third active job over a limit of two is refused with 429."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a", max_active_jobs=2)
    write = await issue_key(engine, "tenant-a", ["transcribe:write"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        ids = [await upload(client, write, PAYLOAD + bytes([i])) for i in range(3)]
        first = await create_job(client, write, ids[0])
        second = await create_job(client, write, ids[1])
        third = await create_job(client, write, ids[2])
    assert first.status_code == 202
    assert second.status_code == 202
    assert third.status_code == 429
    await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S08")
async def test_delete_request_and_result_states(minio: object, pg_url: str) -> None:
    """DELETE marks the job (202, deletion_requested_at set); result is 409 until COMPLETED."""
    engine = make_engine(pg_url)
    await seed_tenant(engine, "tenant-a")
    write = await issue_key(engine, "tenant-a", ["transcribe:write", "transcribe:read"])
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, write, PAYLOAD)
        job_id = (await create_job(client, write, upload_id)).json()["id"]
        early = await client.get(
            f"/v1/transcriptions/{job_id}/result?format=json", headers=auth(write)
        )
        deleted = await client.delete(f"/v1/transcriptions/{job_id}", headers=auth(write))
    assert early.status_code == 409
    assert deleted.status_code == 202
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.system', 'on', true)"))
        marked = await conn.execute(
            text("SELECT deletion_requested_at FROM jobs WHERE id = :id"), {"id": job_id}
        )
        assert marked.scalar_one() is not None
    await engine.dispose()
