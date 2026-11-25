"""Read-side use cases for a tenant's job (S08): get, result. Every read takes the tenant id."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

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
    """Result bodies arrive with S10/S15. Until then a completed job has no body to return."""

    def __init__(self, make_uow: MakeUow) -> None:
        self._make_uow = make_uow

    async def __call__(self, tenant_id: str, job_id: str) -> None:
        job = await GetJob(self._make_uow)(tenant_id, job_id)
        if job.state != JobState.COMPLETED:
            raise ResultNotReadyError
        raise ResultNotAvailableError
