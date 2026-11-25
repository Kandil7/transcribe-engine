"""Worker loop (S06): claim a job, keep its lease alive, run the handler, complete if owned.

The heartbeat runs in its own task, independent of the handler. If it finds the lease lost or
the job cancelled, the handler is cancelled and nothing is written. A handler failure becomes a
domain event: TransientError retries, PermanentError fails the job.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from transcribe_engine.application.ports.queue import JobQueue, Lease
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.domain.jobs import ErrorCode, Job, JobEvent, JobState, Transition, transition

__all__ = ["run_once"]

Handler = Callable[[Job], Awaitable[Transition]]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class WorkerSettings:
    queue_name: str
    owner: str
    lease_for: timedelta
    heartbeat_every: float  # seconds; the design uses 30 s with a 2-minute lease


async def _beat(
    queue: JobQueue, lease: Lease, lease_for: timedelta, every: float, sleep: Sleep
) -> None:
    """Renew the lease until cancelled. Raises LeaseLostError or JobCancelledError to the caller."""
    current = lease
    while True:
        await sleep(every)
        current = await queue.heartbeat(current, lease_for)


def _failure_transition(error: Exception, job: Job) -> Transition:
    event = (
        JobEvent.TRANSIENT_ERROR if isinstance(error, TransientError) else JobEvent.PERMANENT_ERROR
    )
    code = None if event is JobEvent.TRANSIENT_ERROR else ErrorCode.INTERNAL
    return transition(
        JobState.PROCESSING,
        event,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        error_code=code,
    )


async def run_once(
    queue: JobQueue, handler: Handler, settings: WorkerSettings, sleep: Sleep = asyncio.sleep
) -> bool:
    """Claim and process one job. Returns False when nothing was claimable."""
    claimed = await queue.claim(settings.queue_name, settings.owner, settings.lease_for)
    if claimed is None:
        return False
    job, lease = claimed
    work: asyncio.Future[object] = asyncio.ensure_future(handler(job))
    beat: asyncio.Future[object] = asyncio.ensure_future(
        _beat(queue, lease, settings.lease_for, settings.heartbeat_every, sleep)
    )
    done, _ = await asyncio.wait({work, beat}, return_when=asyncio.FIRST_COMPLETED)
    if beat in done:
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        return True  # lease lost or job cancelled: the handler's output is discarded
    beat.cancel()
    await asyncio.gather(beat, return_exceptions=True)
    try:
        result = work.result()
        if not isinstance(result, Transition):
            raise TypeError("handler must return a Transition")
        outcome = result
    except (TransientError, PermanentError) as error:
        outcome = _failure_transition(error, job)
    await queue.complete(lease, outcome)
    return True
