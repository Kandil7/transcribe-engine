"""Delete everything a job owns (S21, D-059), and nothing another owner still needs.

Order: the storage objects go first, inside the open transaction; then the audit row; then the
commit. If a storage delete fails, the transaction is rolled back, so the job and its rows remain
and the call can be repeated. Storage deletes are idempotent, so repeating is safe (AC-5)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field

from transcribe_engine.application.ports.clock import Clock
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.storage import ObjectStorage

__all__ = ["DeleteJobData", "DeletionReport"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]
EVENT = "job.deleted"


@dataclass(frozen=True)
class DeletionReport:
    objects_deleted: int
    rows_deleted: dict[str, int] = field(default_factory=dict)
    result_released: bool = False


class DeleteJobData:
    def __init__(self, make_uow: MakeUow, storage: ObjectStorage, clock: Clock) -> None:
        self._make_uow = make_uow
        self._storage = storage
        self._clock = clock

    async def __call__(self, tenant_id: str, job_id: str) -> DeletionReport:
        at = self._clock.now()
        async with self._make_uow(tenant_id) as uow:
            outcome = await uow.deletions.delete_job(tenant_id, job_id)
            if not outcome.found:
                return DeletionReport(objects_deleted=0)
            objects = await delete_storage(self._storage, outcome.storage_keys)
            await uow.deletions.record_audit(
                tenant_id,
                EVENT,
                job_id,
                at,
                {
                    "objects_deleted": objects,
                    "rows_deleted": dict(outcome.rows_deleted),
                    "result_released": outcome.result_released,
                    "media_released": outcome.media_released,
                },
            )
            await uow.commit()
        return DeletionReport(
            objects_deleted=objects,
            rows_deleted=dict(outcome.rows_deleted),
            result_released=outcome.result_released,
        )


async def delete_storage(storage: ObjectStorage, keys: tuple[str, ...]) -> int:
    """Delete prefixes (keys ending in '/') and single objects. Returns the number removed."""
    removed = 0
    for key in keys:
        if key.endswith("/"):
            removed += await storage.delete_prefix(key)
        elif await storage.delete(key):
            removed += 1
    return removed
