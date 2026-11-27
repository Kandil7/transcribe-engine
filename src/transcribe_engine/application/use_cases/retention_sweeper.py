"""Audio retention (S21, design: الخصوصية ودورة حياة البيانات). A daily sweep removes the audio of
jobs older than their tenant's retention (default 30 days). Transcripts and results stay; only
audio goes.

Each job is handled in its own transaction: its storage objects are deleted first, then the
`audio_deleted_at` marker is set, then the commit. A failure leaves the job due for the next
sweep."""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime

from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.application.use_cases.delete_job_data import delete_storage
from transcribe_engine.domain.errors import DomainError

__all__ = ["RetentionSweeper", "SweepReport"]

_log = logging.getLogger(__name__)

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]


@dataclass(frozen=True)
class SweepReport:
    audio_deleted: int


class RetentionSweeper:
    def __init__(self, make_uow: MakeUow, storage: ObjectStorage) -> None:
        self._make_uow = make_uow
        self._storage = storage

    async def run_once(self, now: datetime) -> SweepReport:
        async with self._make_uow(None) as uow:
            due = await uow.deletions.expired_audio(now)
        swept = 0
        for tenant_id, job_id in due:
            try:
                async with self._make_uow(tenant_id) as uow:
                    keys = await uow.deletions.expire_audio(tenant_id, job_id, now)
                    await delete_storage(self._storage, keys)
                    await uow.commit()
            except (DomainError, ValueError) as exc:
                # One job must not stop the sweep; it stays due for the next run (D-060).
                _log.warning(
                    "audio expiry failed; job stays due",
                    extra={
                        "job_id": job_id,
                        "tenant_id": tenant_id,
                        "error_code": type(exc).__name__,
                    },
                )
                continue
            swept += 1
        return SweepReport(audio_deleted=swept)
