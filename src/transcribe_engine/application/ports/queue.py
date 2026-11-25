"""Job queue port (S06): claim, heartbeat, fenced complete, cancellation, and the reconciler.

Leases are fenced: every write names the owner and the attempt it was claimed with.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from transcribe_engine.domain.jobs import Job, JobStage, Transition

__all__ = ["JobQueue", "Lease", "ReconcileReport", "Reconciler"]


@dataclass(frozen=True)
class Lease:
    job_id: str
    owner: str
    attempt: int
    until: datetime


@dataclass(frozen=True)
class ReconcileReport:
    leases_expired: int
    poisoned: int
    retries_requeued: int


class JobQueue(Protocol):
    async def claim(
        self, queue: str, owner: str, lease_for: timedelta
    ) -> tuple[Job, Lease] | None: ...

    async def heartbeat(self, lease: Lease, extend_by: timedelta) -> Lease:
        """Raises LeaseLostError if the lease no longer matches, JobCancelledError if cancelled."""
        ...

    async def complete(self, lease: Lease, t: Transition, *, stage: JobStage | None = None) -> bool:
        """Fenced write: applies only while owner and attempt still match. False otherwise."""
        ...

    async def is_cancelled(self, job_id: str) -> bool: ...


class Reconciler(Protocol):
    async def run_once(self, now: datetime | None = None) -> ReconcileReport:
        """Expire dead leases, then requeue due retries. Postgres uses database time (D-020)."""
        ...
