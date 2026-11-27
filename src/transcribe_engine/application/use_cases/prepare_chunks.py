"""Prepare the chunk plan on the CPU path (S10, S11).

Runs right after normalization and before the GPU hand-off (IngestJob calls it through its `prepare`
hook). It asks VAD for the speech regions of the normalized audio with the job's own detector
parameters, cuts and merges them into spans no longer than the engine's maximum (S11), turns
any overlapping context into non-overlapping cores, plans the chunks, and stores the plan.
ProcessJob then reads the stored plan, so a restarted job sees the same chunks (AC-7).
"""

import itertools
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager

from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.tracing import Tracer, open_span
from transcribe_engine.application.ports.vad import VoiceActivity
from transcribe_engine.application.use_cases.ingest_job import WAV_NAME
from transcribe_engine.domain.chunks import NORMALIZED_SAMPLE_RATE, SpeechRegion, plan_chunks
from transcribe_engine.domain.jobs import Job, JobStage
from transcribe_engine.domain.storage_keys import work_key
from transcribe_engine.domain.vad import SampleSpan, VadParams, cut_samples, tiles

__all__ = ["PrepareChunks"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]


class PrepareChunks:
    """`max_samples` is the engine's longest chunk. `target_samples` (default: the maximum) is
    the length adjacent regions merge up to. `overlap_samples` is the context shared by windows."""

    def __init__(  # noqa: PLR0913 - one argument per setting; a parameter object would only rename them
        self,
        make_uow: MakeUow,
        vad: VoiceActivity,
        *,
        max_samples: int,
        pad: int,
        target_samples: int | None = None,
        overlap_samples: int = 0,
        tracer: Tracer | None = None,
    ) -> None:
        self._make_uow = make_uow
        self._vad = vad
        self._max_samples = max_samples
        self._pad = pad
        self._target_samples = target_samples if target_samples is not None else max_samples
        self._overlap_samples = overlap_samples
        self._tracer = tracer

    async def __call__(self, job: Job, media_sha256: str) -> None:
        params = VadParams.from_mapping(job.config.vad_params)
        with open_span(self._tracer, job.id, JobStage.VAD.value):
            analysis = await self._vad.analyze(work_key(job.tenant_id, job.id, WAV_NAME), params)
        spans = cut_samples(
            analysis.regions,
            target=self._target_samples,
            cap=self._max_samples,
            pad=self._pad,
            overlap=self._overlap_samples,
            silences=_gaps(analysis.regions),
        )
        cores = [SpeechRegion(span.start_sample, span.end_sample) for span in tiles(spans)]
        chunks = plan_chunks(
            cores,
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


def _gaps(regions: Sequence[SpeechRegion]) -> list[SampleSpan]:
    """The silences between consecutive speech regions: where a long span may be cut."""
    gaps: list[SampleSpan] = []
    for before, after in itertools.pairwise(regions):
        if after.start_sample > before.end_sample:
            gaps.append(SampleSpan(before.end_sample, after.start_sample))
    return gaps
