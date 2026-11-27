"""S22 corrections over HTTP on real Postgres and MinIO.

AC-3 (API part): a stale base version is refused with 409 and a problem document.

Positive control: the save on the current version returns 201 with the next version.

Also covered: an edit that needs alignment is refused with 503 when no aligner is configured (no
invented word times), and a speaker-only save still succeeds because it re-aligns nothing.
"""

import importlib
from types import ModuleType
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.minio import MinioContainer

from tests.integration import api_support

pytestmark = [pytest.mark.integration]


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def _seed_completed_job(pg_engine: Any, tenant: str, job_id: str) -> None:
    """A completed job whose merged transcript is two words: "alpha beta" in segment seg-0."""
    jobs = _mod("transcribe_engine.domain.jobs")
    merge = _mod("transcribe_engine.domain.merge")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    config = _mod("transcribe_engine.domain.config").PipelineConfig(
        engine="faster-whisper",
        model_revision="large-v3@r1",
        language="ar",
        decoding_params={"beam_size": 5},
        vad_params={"threshold": 0.5},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )
    async with uow_mod.SqlUnitOfWork(pg_engine, tenant_id=None) as uow:
        media = await uow.media.upsert(
            jobs.Media(
                id=f"media-{job_id}",
                tenant_id=tenant,
                sha256=("f" + job_id)[:64].ljust(64, "0"),
                storage_key=f"incoming/{tenant}/{job_id}",
                duration_ms=200,
                format="wav",
                size_bytes=4,
            )
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
                config=config,
                result_id=None,
                error_code=None,
                warnings=(),
            )
        )
        await uow.chunks.save_transcript(
            tenant,
            job_id,
            merge.MergedWords(
                words=(
                    merge.Word("alpha", 0, 100, None, 0),
                    merge.Word("beta", 100, 200, None, 0),
                ),
                sample_rate=16000,
            ),
        )
        await uow.commit()


def _client(app_engine: Any, storage: Any, aligner: Any) -> httpx.AsyncClient:
    main = _mod("transcribe_engine.main")
    app = main.build_app(engine=app_engine, storage=storage, aligner=aligner)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _edit(new_text: str) -> dict[str, Any]:
    return {"segment_id": "seg-0", "word_index_from": 1, "word_index_to": 2, "new_text": new_text}


@pytest.mark.xfail(strict=True, reason="S22")
async def test_stale_base_version_is_409(pg_url: str, app_url: str, minio: MinioContainer) -> None:
    """AC-3 (API): the first save on version 1 gives version 2.

    A second save still on version 1 is a 409 with the stale_version problem. Positive control: a
    save on version 2 returns version 3.
    """
    tenant = api_support.new_tenant()
    job = f"s22-{tenant}"
    owner = create_async_engine(pg_url)
    app_engine = create_async_engine(app_url)
    try:
        await api_support.seed_tenant(owner, tenant)
        token = await api_support.issue_key(owner, tenant, ["transcribe:write"])
        await _seed_completed_job(owner, tenant, job)
        aligner = _mod("tests.fakes.aligner").FakeAligner()
        async with _client(app_engine, api_support.storage_for(minio), aligner) as client:
            first = await client.post(
                f"/v1/transcriptions/{job}/versions",
                json={"base_version": 1, "edits": [_edit("gamma")], "speaker_renames": {}},
                headers=api_support.auth(token),
            )
            assert first.status_code == 201, first.text
            assert first.json()["version"] == 2

            stale = await client.post(
                f"/v1/transcriptions/{job}/versions",
                json={"base_version": 1, "edits": [_edit("delta")], "speaker_renames": {}},
                headers=api_support.auth(token),
            )
            assert stale.status_code == 409
            assert stale.json()["code"] == "stale_version"

            current = await client.post(
                f"/v1/transcriptions/{job}/versions",
                json={"base_version": 2, "edits": [_edit("delta")], "speaker_renames": {}},
                headers=api_support.auth(token),
            )
            assert current.status_code == 201
            assert current.json()["version"] == 3
    finally:
        await owner.dispose()
        await app_engine.dispose()


@pytest.mark.xfail(strict=True, reason="S22")
async def test_edit_needing_alignment_is_503_without_aligner(
    pg_url: str, app_url: str, minio: MinioContainer
) -> None:
    """Without an aligner, an edit that needs new word times is refused with 503; nothing is saved.

    Positive control: a speaker-only rename needs no alignment and returns 201.
    """
    tenant = api_support.new_tenant()
    job = f"s22-noal-{tenant}"
    owner = create_async_engine(pg_url)
    app_engine = create_async_engine(app_url)
    try:
        await api_support.seed_tenant(owner, tenant)
        token = await api_support.issue_key(owner, tenant, ["transcribe:write"])
        await _seed_completed_job(owner, tenant, job)
        async with _client(app_engine, api_support.storage_for(minio), None) as client:
            refused = await client.post(
                f"/v1/transcriptions/{job}/versions",
                json={"base_version": 1, "edits": [_edit("gamma")], "speaker_renames": {}},
                headers=api_support.auth(token),
            )
            assert refused.status_code == 503
            assert refused.json()["code"] == "alignment_unavailable"

            renamed = await client.post(
                f"/v1/transcriptions/{job}/versions",
                json={"base_version": 1, "edits": [], "speaker_renames": {"SPEAKER_00": "Ali"}},
                headers=api_support.auth(token),
            )
            assert renamed.status_code == 201, renamed.text
            assert renamed.json()["version"] == 2
    finally:
        await owner.dispose()
        await app_engine.dispose()


@pytest.mark.xfail(strict=True, reason="S22")
async def test_unknown_transcript_is_404(pg_url: str, app_url: str, minio: MinioContainer) -> None:
    """A version save for a job that does not exist is 404, not a silent success."""
    tenant = api_support.new_tenant()
    owner = create_async_engine(pg_url)
    app_engine = create_async_engine(app_url)
    try:
        await api_support.seed_tenant(owner, tenant)
        token = await api_support.issue_key(owner, tenant, ["transcribe:write"])
        aligner = _mod("tests.fakes.aligner").FakeAligner()
        async with _client(app_engine, api_support.storage_for(minio), aligner) as client:
            missing = await client.post(
                "/v1/transcriptions/no-such-job/versions",
                json={"base_version": 1, "edits": [], "speaker_renames": {}},
                headers=api_support.auth(token),
            )
            assert missing.status_code == 404
            assert missing.json()["code"] == "transcript_not_found"
    finally:
        await owner.dispose()
        await app_engine.dispose()
