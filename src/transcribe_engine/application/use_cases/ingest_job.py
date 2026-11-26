"""Ingest an upload for a cpu-queue job (S09): stream and hash it, probe it, admit or refuse it.

The worker calls this for a PENDING_VALIDATION job. Each refusal returns a Transition that fails the
job with a domain code. Refusals are permanent, so nothing retries them: a retry cannot change the
file. Transient tool failures raise, and the worker retries. The file is streamed to scratch storage
while its SHA-256 is computed, so the whole object is never held in memory (D-029).
"""

import hashlib
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

from transcribe_engine.application.ports.media import (
    AudioNormalizer,
    CorruptMediaError,
    MediaInfo,
    MediaProbe,
    UnsupportedMediaError,
)
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.jobs import ErrorCode, Job, JobEvent, JobState, Transition, transition
from transcribe_engine.domain.keys import result_key
from transcribe_engine.domain.media_rules import IngestLimits, admission_error
from transcribe_engine.domain.storage_keys import incoming_key, work_key

__all__ = ["IngestJob"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]
DEFAULT_CHUNK_BYTES = 8 * 2**20
WAV_NAME = "audio.wav"
# Conversion budget: a fixed base plus half a second per second of audio (design: proportional).
CONVERSION_BASE_S = 60.0
CONVERSION_S_PER_MEDIA_S = 0.5


class _RefusedError(Exception):
    """Internal: the file is refused while it is being read. Carries the domain code."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class IngestJob:
    def __init__(  # noqa: PLR0913, PLR0917 - the ports are the wiring; grouping hides it (D-029)
        self,
        make_uow: MakeUow,
        storage: ObjectStorage,
        probe: MediaProbe,
        normalizer: AudioNormalizer,
        scratch_root: Path,
        limits: IngestLimits = IngestLimits(),  # noqa: B008 - frozen dataclass default, never mutated
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    ) -> None:
        self._make_uow = make_uow
        self._storage = storage
        self._probe = probe
        self._normalizer = normalizer
        self._scratch_root = scratch_root
        self._limits = limits
        self._chunk_bytes = chunk_bytes

    async def __call__(self, job: Job) -> Transition:
        key = incoming_key(job.tenant_id, job.media_id)
        head = await self._storage.head(key)
        if head is None:
            return _refuse(job, ErrorCode.INVALID_MEDIA)
        if head.size > self._limits.max_size_bytes:
            return _refuse(job, ErrorCode.TOO_LARGE)
        with tempfile.TemporaryDirectory(dir=self._scratch_root) as scratch:
            source = Path(scratch) / "upload"
            wav = Path(scratch) / WAV_NAME
            try:
                sha256, size = await self._stream_to(key, source)
                info = await self._probe_file(source)
                code = admission_error(info.format_name, info.duration_ms, size, self._limits)
                if code is not None:
                    return _refuse(job, code)
                if await self._finalize_media(job, sha256, info, size):
                    return transition(
                        JobState.PENDING_VALIDATION,
                        JobEvent.CACHE_HIT,
                        attempt_count=job.attempt_count,
                        max_attempts=job.max_attempts,
                    )
                await self._normalize(source, wav, info.duration_ms)
            except _RefusedError as refused:
                return _refuse(job, refused.code)
            await self._storage.put(
                work_key(job.tenant_id, job.id, WAV_NAME), _file_chunks(wav, self._chunk_bytes)
            )
        # Hand-off: the claim keeps the job on cpu until this write; the worker sets queue=gpu.
        return transition(
            JobState.PENDING_VALIDATION,
            JobEvent.VALIDATED,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
        )

    async def _normalize(self, source: Path, target: Path, duration_ms: int) -> None:
        timeout_s = CONVERSION_BASE_S + duration_ms / 1000 * CONVERSION_S_PER_MEDIA_S
        try:
            normalized = await self._normalizer.to_pcm16_mono_16k(
                source, target, timeout_s=timeout_s
            )
        except CorruptMediaError as exc:
            raise _RefusedError(ErrorCode.INVALID_MEDIA) from exc
        except UnsupportedMediaError as exc:
            raise _RefusedError(ErrorCode.UNSUPPORTED_FORMAT) from exc
        # The declared duration is not trusted: check what was actually written (review fix).
        if normalized.duration_ms > self._limits.max_duration_ms:
            raise _RefusedError(ErrorCode.TOO_LONG)
        if normalized.size_bytes > self._limits.max_size_bytes:
            raise _RefusedError(ErrorCode.TOO_LARGE)

    async def _finalize_media(self, job: Job, sha256: str, info: MediaInfo, size: int) -> bool:
        """Record the probed content on the upload's media row and look for a stored result.

        Returns True when a result with this key exists. That result gains one reference, and the
        job completes without the GPU stage (AC-4).
        """
        async with self._make_uow(job.tenant_id) as uow:
            await uow.media.finalize(
                job.media_id, job.tenant_id, sha256, info.duration_ms, info.format_name, size
            )
            cached = await uow.results.get_by_key(result_key(sha256, job.config))
            if cached is not None:
                await uow.results.incr_ref(cached.id, 1)
            await uow.commit()
        return cached is not None

    async def _stream_to(self, key: str, target: Path) -> tuple[str, int]:
        """Copy the object to `target` in chunks, hashing as it goes. Returns (sha256, bytes)."""
        digest = hashlib.sha256()
        size = 0
        with target.open("wb") as handle:
            async for chunk in self._storage.stream(key, self._chunk_bytes):
                size += len(chunk)
                if size > self._limits.max_size_bytes:
                    raise _RefusedError(ErrorCode.TOO_LARGE)
                digest.update(chunk)
                handle.write(chunk)
        return digest.hexdigest(), size

    async def _probe_file(self, source: Path) -> MediaInfo:
        try:
            return await self._probe.probe(source)
        except CorruptMediaError as exc:
            raise _RefusedError(ErrorCode.INVALID_MEDIA) from exc
        except UnsupportedMediaError as exc:
            raise _RefusedError(ErrorCode.UNSUPPORTED_FORMAT) from exc


def _refuse(job: Job, code: ErrorCode) -> Transition:
    return transition(
        JobState.PENDING_VALIDATION,
        JobEvent.VALIDATION_FAILED,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        error_code=code,
    )


async def _file_chunks(path: Path, chunk_bytes: int) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            yield chunk
