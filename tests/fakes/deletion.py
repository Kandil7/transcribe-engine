"""In-memory deletion store for the S21 retention tests. Mirrors the port in
application/ports/deletion.py: expired audio is found by tenant retention and creation time, and
expiring a job's audio returns the storage keys the caller must delete before it commits."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import TracebackType
from typing import Self

from transcribe_engine.application.ports.deletion import DeletionOutcome
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.storage_keys import job_prefix


@dataclass
class _FakeJob:
    tenant_id: str
    job_id: str
    created_at: datetime
    audio_deleted_at: datetime | None = None


@dataclass
class FakeDeletionStore:
    retention_days: dict[str, int] = field(default_factory=dict)
    jobs: dict[str, _FakeJob] = field(default_factory=dict)
    default_retention_days: int = 30

    def add_job(self, tenant_id: str, job_id: str, created_at: datetime) -> None:
        self.jobs[job_id] = _FakeJob(tenant_id, job_id, created_at)

    requested: list[tuple[str, str]] = field(default_factory=list)
    fail_on: set[str] = field(default_factory=set)
    removed: list[str] = field(default_factory=list)

    async def requested_deletions(self) -> tuple[tuple[str, str], ...]:
        return tuple(pair for pair in self.requested if pair[1] not in self.removed)

    async def delete_job(self, tenant_id: str, job_id: str) -> DeletionOutcome:
        if job_id in self.fail_on:
            raise PermanentError("fake refusal for this job")
        self.removed.append(job_id)
        return DeletionOutcome(
            found=True,
            rows_deleted={"jobs": 1},
            result_released=False,
            media_released=False,
            storage_keys=(job_prefix(tenant_id, job_id),),
        )

    async def record_audit(
        self,
        tenant_id: str,
        event: str,
        subject_id: str,
        at: datetime,
        detail: Mapping[str, object],
    ) -> None:
        return None

    def uow(self) -> "_FakeUow":
        return _FakeUow(self)

    async def expired_audio(self, now: datetime) -> tuple[tuple[str, str], ...]:
        due = []
        for job in self.jobs.values():
            days = self.retention_days.get(job.tenant_id, self.default_retention_days)
            if job.audio_deleted_at is None and job.created_at < now - timedelta(days=days):
                due.append((job.tenant_id, job.job_id))
        return tuple(due)

    async def expire_audio(self, tenant_id: str, job_id: str, now: datetime) -> tuple[str, ...]:
        job = self.jobs[job_id]
        job.audio_deleted_at = now
        return (job_prefix(tenant_id, job_id),)

    def audio_deleted_for(self) -> list[str]:
        return sorted(job.job_id for job in self.jobs.values() if job.audio_deleted_at is not None)


class _FakeUow:
    def __init__(self, store: FakeDeletionStore) -> None:
        self.deletions = store

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None
