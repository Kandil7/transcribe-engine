"""Request deletion of a job (S08). It only marks the job; S21 performs the deletion."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime

from transcribe_engine.application.errors import JobNotFoundError
from transcribe_engine.application.ports.clock import Clock
from transcribe_engine.application.ports.repositories import UnitOfWork

__all__ = ["RequestDeletion"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]


class RequestDeletion:
    def __init__(self, make_uow: MakeUow, clock: Clock) -> None:
        self._make_uow = make_uow
        self._clock = clock

    async def __call__(self, tenant_id: str, job_id: str) -> datetime:
        at: datetime = self._clock.now()
        async with self._make_uow(tenant_id) as uow:
            found = await uow.jobs.request_deletion(tenant_id, job_id, at)
            if not found:
                raise JobNotFoundError
            await uow.commit()
        return at
