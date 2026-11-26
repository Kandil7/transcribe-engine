"""Repository ports for jobs, media and results (S05). Infrastructure and fakes implement them.

`apply` is keyed by job id, without tenant (D-017): workers and the reconciler hold the id.
Every other job read takes the tenant id.
"""

from datetime import datetime
from typing import Protocol, Self

from transcribe_engine.application.ports.auth import ApiKeyRepository
from transcribe_engine.application.ports.chunks import ChunkRepository
from transcribe_engine.application.ports.tenancy import IdempotencyRepository, TenantRepository
from transcribe_engine.domain.config import PipelineConfig
from transcribe_engine.domain.jobs import Job, JobStage, JobState, Media, Result, Transition

__all__ = ["JobRepository", "MediaRepository", "ResultRepository", "UnitOfWork"]


class JobRepository(Protocol):
    async def add(self, job: Job) -> None: ...

    async def get(self, tenant_id: str, job_id: str) -> Job | None: ...

    async def request_deletion(self, tenant_id: str, job_id: str, at: datetime) -> bool:
        """Mark the job for deletion (S21 deletes). False if it is not this tenant's job."""
        ...

    async def apply(
        self,
        job_id: str,
        t: Transition,
        *,
        expected: JobState,
        stage: JobStage | None = None,
        attempt_count: int | None = None,
    ) -> bool:
        """Compare-and-set on state. False if the current state is not `expected`.

        `attempt_count`, when given, is written in the same statement (claims increment it, D-019).
        """
        ...


class MediaRepository(Protocol):
    async def upsert(self, media: Media) -> Media:
        """Return the stored media for this sha256, inserting it if new."""
        ...

    async def finalize(
        self,
        media_id: str,
        tenant_id: str,
        sha256: str,
        duration_ms: int,
        format: str,
        size_bytes: int,
    ) -> Media:
        """Give an upload's row its real content once it is probed (S09, D-029).

        If the tenant already holds this sha256, return that row and leave the upload row as it is.
        """
        ...


class ResultRepository(Protocol):
    async def claim_key(
        self, result_key: str, media_id: str, config: PipelineConfig
    ) -> tuple[Result, bool]:
        """Create the result for this key, or return the existing one. The bool is True only for
        the call that created it (INSERT ... ON CONFLICT DO NOTHING RETURNING)."""
        ...

    async def get_by_key(self, result_key: str) -> Result | None: ...

    async def incr_ref(self, result_id: str, delta: int) -> int:
        """Add `delta` to the reference count. Raises PermanentError if it would go negative."""
        ...


class UnitOfWork(Protocol):
    jobs: JobRepository
    media: MediaRepository
    results: ResultRepository
    tenants: TenantRepository
    idempotency: IdempotencyRepository
    api_keys: ApiKeyRepository
    chunks: ChunkRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *exc_info: object) -> None: ...

    async def commit(self) -> None: ...
