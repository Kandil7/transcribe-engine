"""Deletion store port (S21, D-059).

The SQL adapter runs on the unit-of-work connection, so the rows, the released results and the
audit row commit together with the storage deletes that the caller makes before it commits.

Storage keys in an outcome are either a prefix (ends with '/', delete with `delete_prefix`) or one
object key (delete with `delete`)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

__all__ = ["DeletionOutcome", "DeletionStore"]


@dataclass(frozen=True)
class DeletionOutcome:
    found: bool
    rows_deleted: Mapping[str, int]
    result_released: bool
    media_released: bool
    storage_keys: tuple[str, ...]


class DeletionStore(Protocol):
    async def delete_job(self, tenant_id: str, job_id: str) -> DeletionOutcome:
        """Remove the job's rows; release its result and media only when no one else uses them."""
        ...

    async def record_audit(
        self,
        tenant_id: str,
        event: str,
        subject_id: str,
        at: datetime,
        detail: Mapping[str, object],
    ) -> None:
        """One audit row. `detail` holds counts and flags only, never content (AC-3)."""
        ...

    async def expired_audio(self, now: datetime) -> tuple[tuple[str, str], ...]:
        """(tenant, job) pairs whose audio is past the tenant's retention and not yet removed."""
        ...

    async def expire_audio(self, tenant_id: str, job_id: str, now: datetime) -> tuple[str, ...]:
        """Mark the job's audio removed; return the storage keys the caller must delete."""
        ...
