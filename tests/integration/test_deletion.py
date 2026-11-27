"""S21 deletion on real Postgres and MinIO: AC-1 deleting a job removes its objects and rows, AC-2 a
shared result survives until its last owner is deleted, AC-3 the audit row carries no content,
AC-5 deleting twice is safe.

Each check starts from a seeded job whose data is actually present (positive control), so a delete
that does nothing cannot pass.
"""

import contextlib
import importlib
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

import boto3
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.minio import MinioContainer

pytestmark = [pytest.mark.integration, pytest.mark.contract]

MARKER = "ZEBRA-MARKER-7Q"
BUCKET = "deletion-test"
TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _config() -> object:
    config = _mod("transcribe_engine.domain.config")
    return config.PipelineConfig(
        engine="faster-whisper",
        model_revision="large-v3@r1",
        language="ar",
        decoding_params={"beam_size": 5},
        vad_params={"threshold": 0.5},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )


def _storage(minio: MinioContainer) -> Any:
    s3_mod = _mod("transcribe_engine.infrastructure.storage.s3")
    cfg = minio.get_config()
    client = boto3.client(
        "s3",
        endpoint_url=f"http://{cfg['endpoint']}",
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name="us-east-1",
    )
    with contextlib.suppress(client.exceptions.BucketAlreadyOwnedByYou):
        client.create_bucket(Bucket=BUCKET)
    return s3_mod.S3ObjectStorage(client, BUCKET)


async def _seed(
    engine: AsyncEngine,
    storage: object,
    *,
    tenant: str,
    job_id: str,
    sha: str,
    result_key: str,
    cache_hit_of: str | None = None,
) -> str:
    """One completed job with media, result, chunk, transcript and audio objects. Returns result id.
    With `cache_hit_of`, the job points at an existing result and holds a reference to it."""
    jobs = _mod("transcribe_engine.domain.jobs")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    chunks = _mod("transcribe_engine.domain.chunks")
    merge = _mod("transcribe_engine.domain.merge")
    keys = _mod("transcribe_engine.domain.storage_keys")
    upload_id = f"up-{job_id}"
    incoming = keys.incoming_key(tenant, upload_id)
    await storage.put(incoming, b"RIFF")
    await storage.put(keys.work_key(tenant, job_id, "audio.wav"), b"RIFF")
    async with uow_mod.SqlUnitOfWork(engine, tenant_id=None) as uow:
        media = await uow.media.upsert(
            jobs.Media(
                id=f"media-{job_id}",
                tenant_id=tenant,
                sha256=sha,
                storage_key=incoming,
                duration_ms=300,
                format="wav",
                size_bytes=4,
            )
        )
        if cache_hit_of is None:
            result, _ = await uow.results.claim_key(result_key, media.id, _config())
        else:
            result = await uow.results.get_by_key(result_key)
            assert result is not None
        plan = chunks.plan_chunks(
            [chunks.SpeechRegion(0, 300)],
            max_samples=300,
            pad=0,
            total_samples=300,
            sample_rate=16000,
            media_sha256=sha,
            config_hash="cfg",
            job_id=job_id,
        )
        await uow.jobs.add(
            jobs.Job(
                id=job_id,
                tenant_id=tenant,
                media_id=media.id,
                state=jobs.JobState.COMPLETED,
                stage=None,
                attempt_count=1,
                max_attempts=3,
                queue="gpu",
                config=_config(),
                result_id=result.id,
                error_code=None,
                warnings=(),
            )
        )
        await uow.chunks.add_plan(tenant, job_id, plan)
        await uow.chunks.save_result(
            tenant, job_id, plan[0].chunk_id, (merge.RawWord(MARKER, 0, 100, None),)
        )
        await uow.chunks.save_transcript(
            tenant,
            job_id,
            merge.MergedWords(words=(merge.Word(MARKER, 0, 100, None, 0),), sample_rate=16000),
        )
        if cache_hit_of is not None:
            await uow.results.add_reference(tenant, job_id, result.id)
            await uow.results.incr_ref(result.id, 1)
        await uow.commit()
    return result.id


def _make_uow(engine: AsyncEngine) -> Any:
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")

    def make(tenant_id: str | None = None) -> object:
        return uow_mod.SqlUnitOfWork(engine, tenant_id=tenant_id)

    return make


def _clock() -> object:
    return _mod("tests.fakes.clock").FakeClock(current=datetime(2026, 11, 27, tzinfo=UTC))


_COUNT_SQL = {
    "jobs": "SELECT count(*) FROM jobs WHERE id = :job",
    "chunks": "SELECT count(*) FROM chunks WHERE job_id = :job",
    "chunk_results": "SELECT count(*) FROM chunk_results WHERE job_id = :job",
    "transcripts": "SELECT count(*) FROM transcripts WHERE job_id = :job",
    "result_refs": "SELECT count(*) FROM result_refs WHERE job_id = :job",
    "idempotency_keys": "SELECT count(*) FROM idempotency_keys WHERE job_id = :job",
}


async def _count(engine: AsyncEngine, table: str, job_id: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(_COUNT_SQL[table]), {"job": job_id})).scalar_one())


async def _result_exists(engine: AsyncEngine, result_id: str) -> bool:
    async with engine.connect() as conn:
        found = (
            await conn.execute(text("SELECT 1 FROM results WHERE id = :id"), {"id": result_id})
        ).first()
    return found is not None


@pytest.mark.xfail(strict=True, reason="S21")
async def test_delete_removes_everything(pg_url: str, minio: MinioContainer) -> None:
    """AC-1: after DELETE, the job's audio and transcript objects are gone, its rows are gone from
    every table, and its sole result is released. Positive control: before the delete, every table
    holds the job and the audio objects exist."""
    deletion = _mod("transcribe_engine.application.use_cases.delete_job_data")
    keys = _mod("transcribe_engine.domain.storage_keys")
    engine = create_async_engine(pg_url)
    storage = _storage(minio)
    job = "s21-ac1"
    try:
        result_id = await _seed(
            engine, storage, tenant=TENANT_A, job_id=job, sha="a1" * 32, result_key="rk-ac1"
        )
        for table in ("jobs", "chunks", "chunk_results", "transcripts"):
            assert await _count(engine, table, job) >= 1, table
        assert await _result_exists(engine, result_id)
        assert await storage.head(keys.work_key(TENANT_A, job, "audio.wav")) is not None

        use_case = deletion.DeleteJobData(_make_uow(engine), storage, _clock())
        report = await use_case(TENANT_A, job)

        assert report.result_released is True
        assert await storage.head(keys.work_key(TENANT_A, job, "audio.wav")) is None
        for table in (
            "jobs",
            "chunks",
            "chunk_results",
            "transcripts",
            "result_refs",
            "idempotency_keys",
        ):
            assert await _count(engine, table, job) == 0, table
        assert not await _result_exists(engine, result_id)
    finally:
        await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S21")
async def test_shared_result_kept_until_last_owner(pg_url: str, minio: MinioContainer) -> None:
    """AC-2: two tenants hold jobs that share one result. Deleting the first keeps the result (the
    second still uses it). Deleting the last releases it. Positive control: the result exists before
    either delete."""
    deletion = _mod("transcribe_engine.application.use_cases.delete_job_data")
    engine = create_async_engine(pg_url)
    storage = _storage(minio)
    shared_key = "rk-ac2"
    try:
        result_id = await _seed(
            engine,
            storage,
            tenant=TENANT_A,
            job_id="s21-ac2-a",
            sha="b2" * 32,
            result_key=shared_key,
        )
        await _seed(
            engine,
            storage,
            tenant=TENANT_B,
            job_id="s21-ac2-b",
            sha="c3" * 32,
            result_key=shared_key,
            cache_hit_of=result_id,
        )
        assert await _result_exists(engine, result_id)

        first = await deletion.DeleteJobData(_make_uow(engine), storage, _clock())(
            TENANT_A, "s21-ac2-a"
        )
        assert first.result_released is False
        assert await _result_exists(engine, result_id)

        last = await deletion.DeleteJobData(_make_uow(engine), storage, _clock())(
            TENANT_B, "s21-ac2-b"
        )
        assert last.result_released is True
        assert not await _result_exists(engine, result_id)
    finally:
        await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S21")
async def test_audit_row_has_no_content(pg_url: str, minio: MinioContainer) -> None:
    """AC-3: the audit row for a deletion names the job and holds counts only.

    It never holds transcript text (the marker word) or a file name. Positive control: the audit row
    exists."""
    deletion = _mod("transcribe_engine.application.use_cases.delete_job_data")
    engine = create_async_engine(pg_url)
    storage = _storage(minio)
    job = "s21-ac3"
    try:
        await _seed(
            engine, storage, tenant=TENANT_A, job_id=job, sha="d4" * 32, result_key="rk-ac3"
        )
        use_case = deletion.DeleteJobData(_make_uow(engine), storage, _clock())
        await use_case(TENANT_A, job)
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT event, detail::text AS detail FROM audit_log "
                        "WHERE subject_id = :job"
                    ),
                    {"job": job},
                )
            ).all()
        assert len(rows) == 1
        assert rows[0].event == "job.deleted"
        assert MARKER not in rows[0].detail
        assert "up-" not in rows[0].detail
    finally:
        await engine.dispose()


@pytest.mark.xfail(strict=True, reason="S21")
async def test_delete_is_idempotent(pg_url: str, minio: MinioContainer) -> None:
    """AC-5: a second DELETE of the same job succeeds and removes nothing.

    Positive control: the first DELETE does remove the job."""
    deletion = _mod("transcribe_engine.application.use_cases.delete_job_data")
    engine = create_async_engine(pg_url)
    storage = _storage(minio)
    job = "s21-ac5"
    try:
        await _seed(
            engine, storage, tenant=TENANT_A, job_id=job, sha="e5" * 32, result_key="rk-ac5"
        )
        use_case = deletion.DeleteJobData(_make_uow(engine), storage, _clock())
        first = await use_case(TENANT_A, job)
        assert first.objects_deleted >= 1
        assert await _count(engine, "jobs", job) == 0
        second = await use_case(TENANT_A, job)
        assert second.objects_deleted == 0
        assert second.rows_deleted == {}
        assert second.result_released is False
    finally:
        await engine.dispose()
