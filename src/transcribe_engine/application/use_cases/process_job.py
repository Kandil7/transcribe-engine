"""Process a job's chunks on the GPU queue (S10): bounded fan-out, saved per chunk, merged in order.

- Resume: chunks whose result is already stored are skipped (AC-7). A chunk's result is saved as
  soon as it completes, so a crash loses at most the chunks in flight.
- Concurrency is bounded by a semaphore (initially 32, design). Transient ASR errors propagate
  so the worker retries; permanent errors mark only that chunk as failed.
- Partial-failure policy (AC-8): a failed chunk becomes a timed gap with the warning
  `chunk_failed:<idx>` and the job completes; if the tenant requires complete text, the job fails.
- The merged transcript is stored before the job reports success. The worker fences the
  completion; making the two atomic is a follow-up (D-034).
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass, replace

from transcribe_engine.application.ports.asr import ASREngine
from transcribe_engine.application.ports.diarizer import Diarizer
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.tracing import Tracer, open_span
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.domain.jobs import (
    ErrorCode,
    Job,
    JobEvent,
    JobStage,
    JobState,
    Transition,
    Warning,
    chunk_failed_warning,
    transition,
)
from transcribe_engine.domain.merge import ChunkResult, MergedWords, merge, validate_merge
from transcribe_engine.domain.speakers import assign_speakers
from transcribe_engine.domain.storage_keys import work_key

__all__ = ["ProcessJob"]

_log = logging.getLogger(__name__)

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]
WAV = "audio.wav"


@dataclass(frozen=True)
class Diarization:
    """Optional speaker assignment for a job (S17). `split_channels` means the file was split by
    channel, so diarization is skipped (AC-6)."""

    diarizer: Diarizer
    split_channels: bool = False


class ProcessJob:
    def __init__(  # noqa: PLR0913 - one argument per setting; a parameter object would only rename them
        self,
        make_uow: MakeUow,
        asr: ASREngine,
        *,
        language: str = "ar",
        concurrency: int = 32,
        require_complete_text: bool = False,
        diarization: Diarization | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._make_uow = make_uow
        self._asr = asr
        self._language = language
        self._concurrency = concurrency
        self._diarization = diarization
        self._require_complete_text = require_complete_text
        self._tracer = tracer

    async def __call__(self, job: Job) -> Transition:
        tenant = job.tenant_id
        async with self._make_uow(tenant) as uow:
            plan = await uow.chunks.plan(tenant, job.id)
            if not plan and not await uow.chunks.is_prepared(tenant, job.id):
                # The chunk plan is not committed yet: the cpu stage still runs.
                # Completing now would store an empty transcript, so retry (S10 fence).
                raise TransientError("chunk plan is not committed yet")
            stored = await uow.chunks.results(tenant, job.id)
        pending = [chunk for chunk in plan if chunk.chunk_id not in stored]
        failed: set[int] = set()
        gate = asyncio.Semaphore(self._concurrency)
        audio_key = work_key(tenant, job.id, WAV)
        try:
            with self._span(job, JobStage.ASR):
                async with asyncio.TaskGroup() as group:
                    for chunk in pending:
                        group.create_task(self._run_one(job, audio_key, chunk, gate, failed))
        except* TransientError as transient:
            raise transient.exceptions[0] from None
        with self._span(job, JobStage.PERSISTING):
            return await self._finish(job, plan, failed)

    def _span(self, job: Job, stage: JobStage) -> AbstractContextManager[None]:
        return open_span(self._tracer, job.id, stage.value)

    async def _run_one(
        self, job: Job, audio_key: str, chunk: Chunk, gate: asyncio.Semaphore, failed: set[int]
    ) -> None:
        async with gate:
            try:
                words = await self._asr.transcribe(audio_key, chunk, language=self._language)
            except PermanentError:
                failed.add(chunk.idx)
                _log.warning("chunk failed", extra=_fields(job, chunk.idx))
                return
            async with self._make_uow(job.tenant_id) as uow:
                await uow.chunks.save_result(job.tenant_id, job.id, chunk.chunk_id, words)
                await uow.commit()
            _log.info(
                "chunk transcribed", extra={**_fields(job, chunk.idx), "word_count": len(words)}
            )

    async def _finish(self, job: Job, plan: tuple[Chunk, ...], failed: set[int]) -> Transition:
        if failed and self._require_complete_text:
            return transition(
                JobState.PROCESSING,
                JobEvent.PERMANENT_ERROR,
                attempt_count=job.attempt_count,
                max_attempts=job.max_attempts,
                error_code=ErrorCode.INTERNAL,
            )
        tenant = job.tenant_id
        async with self._make_uow(tenant) as uow:
            stored = await uow.chunks.results(tenant, job.id)
            per_chunk = [ChunkResult(c.idx, stored.get(c.chunk_id, ())) for c in plan]
            merged = merge(plan, per_chunk)
        merged, diarization_warnings = await self._diarize(job, merged)
        async with self._make_uow(tenant) as uow:
            await uow.chunks.save_transcript(tenant, job.id, merged)
            await uow.commit()
        warnings = [chunk_failed_warning(idx) for idx in sorted(failed)]
        warnings += diarization_warnings
        warnings += validate_merge(merged, _duration_bound(plan))
        done = transition(
            JobState.PROCESSING,
            JobEvent.SUCCEEDED,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
        )
        return replace(done, warnings=tuple(warnings))

    async def _diarize(self, job: Job, merged: MergedWords) -> tuple[MergedWords, list[str]]:
        """Assign speakers over the whole file (S17).

        A failure keeps the transcript without speakers and adds `diarization_failed`; the job
        still completes (design: partial state)."""
        if self._diarization is None or not job.config.diarization_enabled:
            return merged, []
        if self._diarization.split_channels:  # S13: a channel-split file's channel is its speaker
            return merged, []
        try:
            diarizer = self._diarization.diarizer
            turns = await diarizer.diarize(work_key(job.tenant_id, job.id, WAV), None)
        except (TransientError, PermanentError):
            _log.warning("diarization failed", extra=_fields(job, -1))
            return merged, [Warning.DIARIZATION_FAILED.value]
        return replace(merged, words=assign_speakers(merged.words, turns)), []


def _fields(job: Job, chunk_idx: int) -> dict[str, object]:
    """Log fields for a chunk: ids and numbers only, never transcript text (S20, AC-5)."""
    return {
        "job_id": job.id,
        "tenant_id": job.tenant_id,
        "stage": JobStage.ASR.value,
        "attempt": job.attempt_count,
        "chunk_idx": chunk_idx,
    }


def _duration_bound(plan: tuple[Chunk, ...]) -> int:
    """Upper bound of the file in samples: the last core plus its padding."""
    if not plan:
        return 0
    last = plan[-1]
    return last.end_sample + last.pad_after
