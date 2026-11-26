"""Read-side use cases for a tenant's job (S08): get, result. Every read takes the tenant id."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from transcribe_engine.application.errors import (
    JobNotFoundError,
    ResultNotAvailableError,
    ResultNotReadyError,
)
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.domain.jobs import Job, JobState

__all__ = ["GetJob", "GetResult"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]


class GetJob:
    def __init__(self, make_uow: MakeUow) -> None:
        self._make_uow = make_uow

    async def __call__(self, tenant_id: str, job_id: str) -> Job:
        async with self._make_uow(tenant_id) as uow:
            job = await uow.jobs.get(tenant_id, job_id)
        if job is None:
            raise JobNotFoundError
        return job


class GetResult:
    """The stored transcript of a completed job (S10). Word-level until S15 adds segments."""

    def __init__(self, make_uow: MakeUow) -> None:
        self._make_uow = make_uow

    async def __call__(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        job = await GetJob(self._make_uow)(tenant_id, job_id)
        if job.state != JobState.COMPLETED:
            raise ResultNotReadyError
        async with self._make_uow(tenant_id) as uow:
            merged = await uow.chunks.transcript(tenant_id, job_id)
        if merged is None:
            raise ResultNotAvailableError
        return {
            "id": job_id,
            "format": "json",
            "language": job.config.language,
            "warnings": list(job.warnings),
            "words": [
                {
                    "text": word.text,
                    "start_ms": word.start_ms,
                    "end_ms": word.end_ms,
                    "conf": word.conf,
                    "chunk_idx": word.chunk_idx,
                }
                for word in merged.words
            ],
        }
