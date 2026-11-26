"""In-memory repositories and unit of work for the contract tests (S05).

All units of work from one FakeStore share data. Writes are immediate; there is no rollback,
which the contract tests do not rely on. Errors follow the Postgres adapter: duplicates and refused
reference changes raise PermanentError (D-019).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Self

from transcribe_engine.application.ports.queue import Lease
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.config import PipelineConfig
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.jobs import Job, JobStage, JobState, Media, Result, Transition
from transcribe_engine.domain.merge import MergedWords, RawWord


@dataclass
class FakeStore:
    jobs: dict[str, Job] = field(default_factory=dict)
    media_by_tenant_sha: dict[tuple[str, str], Media] = field(default_factory=dict)
    results_by_key: dict[str, Result] = field(default_factory=dict)
    leases: dict[str, Lease] = field(default_factory=dict)  # job id -> current lease (S06)
    chunk_plans: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    chunk_results: dict[tuple[str, str, str], tuple[object, ...]] = field(default_factory=dict)
    transcripts: dict[tuple[str, str], object] = field(default_factory=dict)


class FakeJobRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def add(self, job: Job) -> None:
        if job.id in self._store.jobs:
            raise PermanentError("database rejected the write")
        self._store.jobs[job.id] = job

    async def get(self, tenant_id: str, job_id: str) -> Job | None:
        job = self._store.jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            return None
        return job

    async def apply(
        self,
        job_id: str,
        t: Transition,
        *,
        expected: JobState,
        stage: JobStage | None = None,
        attempt_count: int | None = None,
    ) -> bool:
        job = self._store.jobs.get(job_id)
        if job is None or job.state != expected:
            return False
        self._store.jobs[job_id] = replace(
            job,
            state=t.to,
            error_code=t.error_code,
            stage=stage or job.stage,
            attempt_count=attempt_count if attempt_count is not None else job.attempt_count,
        )
        return True


class FakeMediaRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def upsert(self, media: Media) -> Media:
        """Dedupe is per tenant (D-019): the same bytes from another tenant are a new row."""
        key = (media.tenant_id, media.sha256)
        return self._store.media_by_tenant_sha.setdefault(key, media)

    async def finalize(
        self,
        media_id: str,
        tenant_id: str,
        sha256: str,
        duration_ms: int,
        format: str,
        size_bytes: int,
    ) -> Media:
        """D-029: the upload row takes the content, unless the tenant already holds this sha."""
        existing = self._store.media_by_tenant_sha.get((tenant_id, sha256))
        if existing is not None:
            return existing
        for key, row in list(self._store.media_by_tenant_sha.items()):
            if row.id == media_id and row.tenant_id == tenant_id:
                updated = replace(
                    row,
                    sha256=sha256,
                    duration_ms=duration_ms,
                    format=format,
                    size_bytes=size_bytes,
                )
                del self._store.media_by_tenant_sha[key]
                self._store.media_by_tenant_sha[(tenant_id, sha256)] = updated
                return updated
        raise PermanentError("media row not found")


class FakeResultRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def claim_key(
        self, result_key: str, media_id: str, config: PipelineConfig
    ) -> tuple[Result, bool]:
        existing = self._store.results_by_key.get(result_key)
        if existing is not None:
            return existing, False
        created = Result(
            id=result_key, result_key=result_key, media_id=media_id, config=config, ref_count=0
        )
        self._store.results_by_key[result_key] = created
        return created, True

    async def get_by_key(self, result_key: str) -> Result | None:
        return self._store.results_by_key.get(result_key)

    async def incr_ref(self, result_id: str, delta: int) -> int:
        for key, result in self._store.results_by_key.items():
            if result.id == result_id:
                if result.ref_count + delta < 0:
                    raise PermanentError("result reference change refused")
                updated = replace(result, ref_count=result.ref_count + delta)
                self._store.results_by_key[key] = updated
                return updated.ref_count
        raise PermanentError("result reference change refused")


class FakeChunkRepository:
    """Chunk plan, results and transcript (S10). Tenant-scoped like the Postgres adapter."""

    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def add_plan(self, tenant_id: str, job_id: str, chunks: Sequence[Chunk]) -> None:
        plan = self._store.chunk_plans.setdefault((tenant_id, job_id), {})
        for chunk in chunks:
            plan.setdefault(chunk.chunk_id, chunk)

    async def plan(self, tenant_id: str, job_id: str) -> tuple[Chunk, ...]:
        stored = self._store.chunk_plans.get((tenant_id, job_id), {})
        return tuple(sorted(stored.values(), key=lambda chunk: chunk.idx))  # type: ignore[attr-defined]

    async def save_result(
        self, tenant_id: str, job_id: str, chunk_id: str, words: tuple[RawWord, ...]
    ) -> None:
        self._store.chunk_results[(tenant_id, job_id, chunk_id)] = words

    async def results(self, tenant_id: str, job_id: str) -> dict[str, tuple[RawWord, ...]]:
        return {
            chunk_id: words
            for (tid, jid, chunk_id), words in self._store.chunk_results.items()
            if tid == tenant_id and jid == job_id
        }  # type: ignore[return-value]

    async def save_transcript(self, tenant_id: str, job_id: str, merged: MergedWords) -> None:
        self._store.transcripts[(tenant_id, job_id)] = merged

    async def transcript(self, tenant_id: str, job_id: str) -> MergedWords | None:
        return self._store.transcripts.get((tenant_id, job_id))  # type: ignore[return-value]


class FakeUnitOfWork:
    def __init__(self, store: FakeStore) -> None:
        self.jobs = FakeJobRepository(store)
        self.media = FakeMediaRepository(store)
        self.results = FakeResultRepository(store)
        self.chunks = FakeChunkRepository(store)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def commit(self) -> None:
        return None
