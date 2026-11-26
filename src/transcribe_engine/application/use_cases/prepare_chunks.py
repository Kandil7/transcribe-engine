"""Prepare the chunk plan on the CPU path (S10).

Runs right after normalization and before the GPU hand-off (IngestJob calls it through its `prepare`
hook). It asks VAD for the speech regions of the normalized audio, plans the chunks, and stores the
plan. ProcessJob then reads the stored plan, so a restarted job sees the same chunks (AC-7).
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.vad import VoiceActivity
from transcribe_engine.application.use_cases.ingest_job import WAV_NAME
from transcribe_engine.domain.chunks import NORMALIZED_SAMPLE_RATE, plan_chunks
from transcribe_engine.domain.jobs import Job
from transcribe_engine.domain.storage_keys import work_key

__all__ = ["PrepareChunks"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]


class PrepareChunks:
    def __init__(
        self,
        make_uow: MakeUow,
        vad: VoiceActivity,
        *,
        max_samples: int,
        pad: int,
    ) -> None:
        self._make_uow = make_uow
        self._vad = vad
        self._max_samples = max_samples
        self._pad = pad

    async def __call__(self, job: Job, media_sha256: str) -> None:
        analysis = await self._vad.analyze(work_key(job.tenant_id, job.id, WAV_NAME))
        chunks = plan_chunks(
            analysis.regions,
            max_samples=self._max_samples,
            pad=self._pad,
            total_samples=analysis.total_samples,
            sample_rate=NORMALIZED_SAMPLE_RATE,
            media_sha256=media_sha256,
            config_hash=job.config.config_hash(),
            job_id=job.id,
        )
        async with self._make_uow(job.tenant_id) as uow:
            await uow.chunks.add_plan(job.tenant_id, job.id, chunks)
            await uow.commit()
