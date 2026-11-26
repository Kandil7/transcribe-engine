"""Contract tests for the repositories and unit of work (S05). Run against the in-memory fakes and
real Postgres (Testcontainers, migrations applied with Alembic).

Imports happen inside each test body except the test-infrastructure ones at the top.
"""

import asyncio
import hashlib
import importlib
import re
from collections.abc import Callable
from types import ModuleType

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.contract]

KINDS = ["fake", "postgres"]


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _backend(kind: str, pg_url: str) -> tuple[Callable[[], object], Callable[[str], object]]:
    """Unit-of-work factory and a row counter for one backend.

    The fake shares one store across units of work. The counter answers "how many result rows
    carry this key", which is what the one-row contract means.
    """
    if kind == "fake":
        fakes = _mod("tests.fakes.repositories")
        store = fakes.FakeStore()

        async def fake_count(key: str) -> int:
            return sum(1 for stored in store.results_by_key.values() if stored.result_key == key)

        return (lambda: fakes.FakeUnitOfWork(store)), fake_count
    sql_uow = _mod("transcribe_engine.infrastructure.db.uow")
    session = _mod("transcribe_engine.infrastructure.db.session")
    engine = session.make_engine(pg_url)

    async def pg_count(key: str) -> int:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT count(*) FROM results WHERE result_key = :key"), {"key": key}
            )
            return int(result.scalar_one())

    return (lambda: sql_uow.SqlUnitOfWork(engine, tenant_id=None)), pg_count


def _config(vad_threshold: float = 0.5) -> object:
    config = _mod("transcribe_engine.domain.config")
    return config.PipelineConfig(
        engine="faster-whisper",
        model_revision="large-v3@r1",
        language="ar",
        decoding_params={"beam_size": 5, "temperature": 0},
        vad_params={"threshold": vad_threshold},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )


def _job(job_id: str, tenant_id: str, media_id: str, **overrides: object) -> object:
    jobs = _mod("transcribe_engine.domain.jobs")
    fields: dict[str, object] = {
        "id": job_id,
        "tenant_id": tenant_id,
        "media_id": media_id,
        "state": jobs.JobState.QUEUED,
        "stage": None,
        "attempt_count": 0,
        "max_attempts": 3,
        "queue": "cpu",
        "config": _config(),
        "result_id": None,
        "error_code": None,
        "warnings": (),
    }
    fields.update(overrides)
    return jobs.Job(**fields)  # type: ignore[arg-type]


def _media(media_id: str, tenant_id: str = "tenant-a", seed: str = "") -> object:
    jobs = _mod("transcribe_engine.domain.jobs")
    return jobs.Media(
        id=media_id,
        tenant_id=tenant_id,
        sha256=hashlib.sha256((seed or media_id).encode()).hexdigest(),
        storage_key=f"incoming/{tenant_id}/upload-{media_id}",
        duration_ms=60_000,
        format="mp3",
        size_bytes=1_000_000,
    )


async def test_state_check_matches_domain(pg_url: str) -> None:
    """AC-1: the ck_jobs_state constraint lists exactly the JobState values."""
    jobs = _mod("transcribe_engine.domain.jobs")
    engine = create_async_engine(pg_url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                    "WHERE c.conname = 'ck_jobs_state'"
                )
            )
            definitions = [row[0] for row in rows]
    finally:
        await engine.dispose()
    assert len(definitions) == 1
    states = set(re.findall(r"'([A-Z_]+)'", definitions[0]))
    assert states == {state.value for state in jobs.JobState}


@pytest.mark.parametrize("kind", KINDS)
async def test_claim_key_concurrent(kind: str, pg_url: str) -> None:
    """AC-2: 20 concurrent claims on one key give one creator, 19 readers and exactly one row."""
    make, count_rows = _backend(kind, pg_url)
    config = _config()
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-1"))  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]

    gate = asyncio.Event()

    async def claim() -> tuple[bool, str]:
        await gate.wait()  # all claimants reach the gate before any proceeds
        async with make() as uow:  # type: ignore[attr-defined]
            result, created = await uow.results.claim_key(  # type: ignore[attr-defined]
                "res_concurrent", "media-1", config
            )
            await uow.commit()  # type: ignore[attr-defined]
            return created, result.id

    tasks = [asyncio.create_task(claim()) for _ in range(20)]
    await asyncio.sleep(0)
    gate.set()
    outcomes = await asyncio.gather(*tasks)
    assert sum(1 for created, _ in outcomes if created) == 1
    assert len({result_id for _, result_id in outcomes}) == 1
    assert await count_rows("res_concurrent") == 1


@pytest.mark.parametrize("kind", KINDS)
async def test_apply_compare_and_set(kind: str, pg_url: str) -> None:
    """AC-3: a stale expected state returns False and changes nothing, including stage and error."""
    jobs = _mod("transcribe_engine.domain.jobs")
    make, _ = _backend(kind, pg_url)
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-2"))  # type: ignore[attr-defined]
        await uow.jobs.add(_job("job-cas", "tenant-a", "media-2"))  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    claimed = jobs.transition(
        jobs.JobState.QUEUED, jobs.JobEvent.CLAIMED, attempt_count=1, max_attempts=3
    )
    stale = jobs.transition(
        jobs.JobState.PROCESSING,
        jobs.JobEvent.PERMANENT_ERROR,
        attempt_count=1,
        max_attempts=3,
        error_code=jobs.ErrorCode.INVALID_MEDIA,
    )
    async with make() as uow:  # type: ignore[attr-defined]
        assert await uow.jobs.apply(  # type: ignore[attr-defined]
            "job-cas", claimed, expected=jobs.JobState.QUEUED, attempt_count=1
        )
        assert not await uow.jobs.apply(  # type: ignore[attr-defined]
            "job-cas",
            stale,
            expected=jobs.JobState.QUEUED,
            stage=jobs.JobStage.VALIDATING,
        )
        await uow.commit()  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        job = await uow.jobs.get("tenant-a", "job-cas")  # type: ignore[attr-defined]
    assert job is not None
    assert job.state == jobs.JobState.PROCESSING
    assert job.error_code is None
    assert job.stage is None
    assert job.attempt_count == 1


@pytest.mark.parametrize("kind", KINDS)
async def test_get_other_tenant_returns_none(kind: str, pg_url: str) -> None:
    """AC-4: a job is invisible to other tenants."""
    make, _ = _backend(kind, pg_url)
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-3"))  # type: ignore[attr-defined]
        await uow.jobs.add(_job("job-iso", "tenant-a", "media-3"))  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        assert await uow.jobs.get("tenant-b", "job-iso") is None  # type: ignore[attr-defined]
        assert await uow.jobs.get("tenant-a", "job-iso") is not None  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", KINDS)
async def test_job_round_trip(kind: str, pg_url: str) -> None:
    """AC-5: every field survives save and load, including non-null stage, error, result, warnings,
    attempt_count, and a float that JSONB would render differently (1e20)."""
    jobs = _mod("transcribe_engine.domain.jobs")
    config_mod = _mod("transcribe_engine.domain.config")
    make, _ = _backend(kind, pg_url)
    rich_config = config_mod.PipelineConfig(
        engine="faster-whisper",
        model_revision="large-v3@r1",
        language="ar",
        decoding_params={"beam_size": 5, "temperature": 0.5},
        vad_params={"threshold": 0.5, "scale": 1e20},
        diarization_enabled=True,
        pipeline_version="1.0.0",
    )
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-4"))  # type: ignore[attr-defined]
        claimed_result, _ = await uow.results.claim_key(  # type: ignore[attr-defined]
            "res_rt", "media-4", rich_config
        )
        await uow.commit()  # type: ignore[attr-defined]
    original = _job(
        "job-rt",
        "tenant-a",
        "media-4",
        state=jobs.JobState.FAILED,
        stage=jobs.JobStage.ASR,
        attempt_count=2,
        config=rich_config,
        result_id=claimed_result.id,
        error_code=jobs.ErrorCode.TIMEOUT,
        warnings=("low_snr", "chunk_failed:3"),
    )
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.jobs.add(original)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        loaded = await uow.jobs.get("tenant-a", "job-rt")  # type: ignore[attr-defined]
    assert loaded == original
    assert loaded.config.canonical_json() == original.config.canonical_json()  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", KINDS)
async def test_media_dedupe_is_per_tenant(kind: str, pg_url: str) -> None:
    """Same bytes for two tenants are two media rows; within one tenant they are one (D-019)."""
    make, _ = _backend(kind, pg_url)
    async with make() as uow:  # type: ignore[attr-defined]
        first = await uow.media.upsert(_media("m-a", "tenant-a", seed="same-bytes"))  # type: ignore[attr-defined]
        again = await uow.media.upsert(_media("m-a2", "tenant-a", seed="same-bytes"))  # type: ignore[attr-defined]
        other = await uow.media.upsert(_media("m-b", "tenant-b", seed="same-bytes"))  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    assert again.id == first.id
    assert other.id != first.id
    assert other.tenant_id == "tenant-b"
    assert other.storage_key.startswith("incoming/tenant-b/")


@pytest.mark.parametrize("kind", KINDS)
async def test_result_lookup_and_reference_counts(kind: str, pg_url: str) -> None:
    """get_by_key finds the claimed result; ref counts move and never go negative."""
    make, _ = _backend(kind, pg_url)
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-5"))  # type: ignore[attr-defined]
        created, _ = await uow.results.claim_key("res_refs", "media-5", _config())  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    domain_errors = _mod("transcribe_engine.domain.errors")
    async with make() as uow:  # type: ignore[attr-defined]
        found = await uow.results.get_by_key("res_refs")  # type: ignore[attr-defined]
        assert found is not None
        assert found.id == created.id
        assert await uow.results.get_by_key("res_missing") is None  # type: ignore[attr-defined]
        assert await uow.results.incr_ref(created.id, 2) == 2  # type: ignore[attr-defined]
        with pytest.raises(domain_errors.PermanentError):
            await uow.results.incr_ref(created.id, -3)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        after = await uow.results.get_by_key("res_refs")  # type: ignore[attr-defined]
    assert after is not None
    assert after.ref_count == 2


@pytest.mark.parametrize("kind", KINDS)
async def test_refused_writes_are_permanent_errors(kind: str, pg_url: str) -> None:
    """Unknown result ids and duplicate job ids are refused as PermanentError on both backends."""
    domain_errors = _mod("transcribe_engine.domain.errors")
    make, _ = _backend(kind, pg_url)
    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(_media("media-6"))  # type: ignore[attr-defined]
        await uow.jobs.add(_job("job-dup", "tenant-a", "media-6"))  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    async with make() as uow:  # type: ignore[attr-defined]
        with pytest.raises(domain_errors.PermanentError):
            await uow.results.incr_ref("no-such-result", 1)  # type: ignore[attr-defined]
    # The translation happens in __aexit__, so the expectation wraps the whole unit of work.
    with pytest.raises(domain_errors.PermanentError):
        async with make() as uow:  # type: ignore[attr-defined]
            await uow.jobs.add(_job("job-dup", "tenant-a", "media-6"))  # type: ignore[attr-defined]


@pytest.mark.xfail(strict=True, reason="S09")
@pytest.mark.parametrize("kind", KINDS)
async def test_finalize_fills_the_upload_row_or_returns_the_existing_one(
    kind: str, pg_url: str
) -> None:
    """S09 (D-029). An upload row with a placeholder sha takes the real content. A sha the tenant
    already has returns that row, and the upload row keeps its placeholder."""
    media_cls = _mod("transcribe_engine.domain.jobs").Media
    real = hashlib.sha256(b"same-content").hexdigest()
    make, _ = _backend(kind, pg_url)

    def upload(media_id: str) -> object:
        return media_cls(
            id=media_id,
            tenant_id="tenant-a",
            sha256=f"upload:{media_id}",
            storage_key=f"incoming/tenant-a/{media_id}",
            duration_ms=0,
            format="unknown",
            size_bytes=12,
        )

    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(upload("up-1"))  # type: ignore[attr-defined]
        first = await uow.media.finalize("up-1", "tenant-a", real, 1500, "mp3", 12)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    assert first.id == "up-1"
    assert first.sha256 == real
    assert first.duration_ms == 1500
    assert first.format == "mp3"

    async with make() as uow:  # type: ignore[attr-defined]
        await uow.media.upsert(upload("up-2"))  # type: ignore[attr-defined]
        again = await uow.media.finalize("up-2", "tenant-a", real, 1500, "mp3", 12)  # type: ignore[attr-defined]
        await uow.commit()  # type: ignore[attr-defined]
    assert again.id == "up-1"
