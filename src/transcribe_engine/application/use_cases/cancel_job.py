"""Cancel a job (S08): CANCEL_REQUESTED from the domain table, applied as a CAS (D-017)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from transcribe_engine.application.errors import JobAlreadyTerminalError, JobNotFoundError
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.domain.jobs import Job, JobEvent, transition

__all__ = ["CancelJob"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]


class CancelJob:
    def __init__(self, make_uow: MakeUow) -> None:
        self._make_uow = make_uow

    async def __call__(self, tenant_id: str, job_id: str) -> Job:
        async with self._make_uow(tenant_id) as uow:
            job = await uow.jobs.get(tenant_id, job_id)
            if job is None:
                raise JobNotFoundError
            if job.state.is_terminal:
                raise JobAlreadyTerminalError
            decision = transition(
                job.state,
                JobEvent.CANCEL_REQUESTED,
                attempt_count=job.attempt_count,
                max_attempts=job.max_attempts,
            )
            applied = await uow.jobs.apply(job.id, decision, expected=job.state)
            if not applied:  # the job moved between the read and the write
                raise JobAlreadyTerminalError
            await uow.commit()
            updated = await uow.jobs.get(tenant_id, job_id)
        if updated is None:
            raise JobNotFoundError
        return updated
