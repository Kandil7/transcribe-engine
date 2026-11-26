"""S09 ingest use case on fakes: AC-3 (too long), AC-4 (cache hit), AC-5 (streamed hash),
AC-7 (hand-off).

Each refusal is paired with a positive control (a valid file reaches QUEUED), so a handler
that always refuses cannot pass. Imports happen inside helpers so the module collects before the
code exists.
"""

import hashlib
import importlib
from types import ModuleType
from typing import Any

MAX_DURATION_MS = 3 * 3600 * 1000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _config() -> Any:
    config = _mod("transcribe_engine.domain.config")
    return config.PipelineConfig(
        engine="faster-whisper",
        model_revision="pending-s00",
        language="ar",
        decoding_params={"temperature": 0.0},
        vad_params={},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )


def _job() -> Any:
    jobs = _mod("transcribe_engine.domain.jobs")
    return jobs.Job(
        id="job-1",
        tenant_id="tenant-a",
        media_id="upload-a",
        state=jobs.JobState.PENDING_VALIDATION,
        stage=None,
        attempt_count=1,
        max_attempts=3,
        queue="cpu",
        config=_config(),
        result_id=None,
        error_code=None,
        warnings=(),
    )


class _RecordingStorage:
    """Wraps the fake storage and records every chunk the ingest handler reads."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.chunk_sizes: list[int] = []
        self.stream_args: list[int] = []

    async def head(self, key: str) -> Any:
        return await self.inner.head(key)

    async def stream(self, key: str, chunk_bytes: int = 8 * 2**20) -> Any:
        self.stream_args.append(chunk_bytes)
        async for chunk in self.inner.stream(key, chunk_bytes):
            self.chunk_sizes.append(len(chunk))
            yield chunk

    async def put(self, key: str, data: Any) -> None:
        await self.inner.put(key, data)


async def _world(
    upload: bytes, *, probe_info: Any = None, probe_error: Exception | None = None
) -> tuple[Any, ...]:
    fakes_repo = _mod("tests.fakes.repositories")
    fakes_storage = _mod("tests.fakes.storage")
    fakes_media = _mod("tests.fakes.media")
    media = _mod("transcribe_engine.application.ports.media")
    store = fakes_repo.FakeStore()
    # The row create_job writes for every upload, before the ingest handler runs.
    upload_row = _mod("transcribe_engine.domain.jobs").Media(
        id="upload-a",
        tenant_id="tenant-a",
        sha256="upload:upload-a",
        storage_key="incoming/tenant-a/upload-a",
        duration_ms=0,
        format="unknown",
        size_bytes=len(upload),
    )
    store.media_by_tenant_sha[("tenant-a", "upload:upload-a")] = upload_row
    inner = fakes_storage.FakeObjectStorage()
    await inner.put("incoming/tenant-a/upload-a", upload)
    storage = _RecordingStorage(inner)
    info = probe_info or media.MediaInfo(
        format_name="mp3", duration_ms=1_000, sample_rate=44_100, channels=2, size_bytes=len(upload)
    )
    probe = fakes_media.FakeMediaProbe(info=info, error=probe_error)
    normalizer = fakes_media.FakeAudioNormalizer(
        output=media.NormalizedAudio(
            duration_ms=1_000, sample_rate=16_000, channels=1, size_bytes=32_000
        )
    )

    def make_uow(tenant_id: str | None = None) -> Any:
        return fakes_repo.FakeUnitOfWork(store)

    return store, inner, storage, probe, normalizer, make_uow


def _ingest(
    storage: Any, probe: Any, normalizer: Any, make_uow: Any, tmp_path: Any, **kwargs: Any
) -> Any:
    ingest = _mod("transcribe_engine.application.use_cases.ingest_job")
    return ingest.IngestJob(
        make_uow=make_uow,
        storage=storage,
        probe=probe,
        normalizer=normalizer,
        scratch_root=tmp_path,
        **kwargs,
    )


async def test_too_long_fails_permanently(tmp_path: Any) -> None:
    """AC-3. Positive control: a 1 s file in the same setup reaches QUEUED (hand-off test)."""
    media = _mod("transcribe_engine.application.ports.media")
    jobs = _mod("transcribe_engine.domain.jobs")
    info = media.MediaInfo("mp3", MAX_DURATION_MS + 1, 44_100, 2, 10)
    _, _, storage, probe, normalizer, make_uow = await _world(b"x" * 10, probe_info=info)
    transition = await _ingest(storage, probe, normalizer, make_uow, tmp_path)(_job())
    assert transition.to is jobs.JobState.FAILED
    assert transition.error_code is jobs.ErrorCode.TOO_LONG
    assert normalizer.calls == []  # nothing is converted for a refused file


async def test_cache_hit_completes_without_gpu(tmp_path: Any) -> None:
    """AC-4. A stored result for (file sha, config) completes the job and adds one reference."""
    jobs = _mod("transcribe_engine.domain.jobs")
    keys = _mod("transcribe_engine.domain.keys")
    upload = b"RIFF-same-bytes"
    store, inner, storage, probe, normalizer, make_uow = await _world(upload)
    key = keys.result_key(hashlib.sha256(upload).hexdigest(), _config())
    store.results_by_key[key] = jobs.Result(
        id=key, result_key=key, media_id="old-media", config=_config(), ref_count=2
    )
    transition = await _ingest(storage, probe, normalizer, make_uow, tmp_path)(_job())
    assert transition.to is jobs.JobState.COMPLETED
    assert store.results_by_key[key].ref_count == 3
    assert normalizer.calls == []
    assert await inner.head("work/tenant-a/job-1/audio.wav") is None


async def test_hash_streamed(tmp_path: Any) -> None:
    """AC-5. The file is read in stream chunks; no single read is larger than the chunk size."""
    upload = b"a" * 5_000
    _, _, storage, probe, normalizer, make_uow = await _world(upload)
    ingest = _ingest(storage, probe, normalizer, make_uow, tmp_path, chunk_bytes=1_024)
    await ingest(_job())
    assert storage.stream_args == [1_024]
    assert len(storage.chunk_sizes) > 1
    assert max(storage.chunk_sizes) <= 1_024
    assert sum(storage.chunk_sizes) == len(upload)


async def test_handoff_to_gpu_queue(tmp_path: Any) -> None:
    """AC-7. A valid file ends in QUEUED (the worker sets queue=gpu); the WAV is in work/."""
    jobs = _mod("transcribe_engine.domain.jobs")
    _, inner, storage, probe, normalizer, make_uow = await _world(b"RIFF-valid")
    transition = await _ingest(storage, probe, normalizer, make_uow, tmp_path)(_job())
    assert transition.to is jobs.JobState.QUEUED
    assert transition.error_code is None
    assert await inner.head("work/tenant-a/job-1/audio.wav") is not None
    assert len(normalizer.calls) == 1


async def test_normalized_output_too_long_is_refused(tmp_path: Any) -> None:
    """Review fix (S09). The declared duration is not trusted: a written WAV over the limit is
    refused as TOO_LONG. The fake normalizer stands for an output that exceeds the limit."""
    media = _mod("transcribe_engine.application.ports.media")
    jobs = _mod("transcribe_engine.domain.jobs")
    _, _, storage, probe, normalizer, make_uow = await _world(b"RIFF-long")
    normalizer.output = media.NormalizedAudio(
        duration_ms=MAX_DURATION_MS + 1, sample_rate=16_000, channels=1, size_bytes=32_000
    )
    transition = await _ingest(storage, probe, normalizer, make_uow, tmp_path)(_job())
    assert transition.to is jobs.JobState.FAILED
    assert transition.error_code is jobs.ErrorCode.TOO_LONG


async def test_normalized_output_too_large_is_refused(tmp_path: Any) -> None:
    """Review fix (S09). An output over the byte limit is refused as TOO_LARGE."""
    media = _mod("transcribe_engine.application.ports.media")
    jobs = _mod("transcribe_engine.domain.jobs")
    limits = _mod("transcribe_engine.domain.media_rules").IngestLimits()
    _, _, storage, probe, normalizer, make_uow = await _world(b"RIFF-big")
    normalizer.output = media.NormalizedAudio(
        duration_ms=1_000, sample_rate=16_000, channels=1, size_bytes=limits.max_size_bytes + 1
    )
    transition = await _ingest(storage, probe, normalizer, make_uow, tmp_path)(_job())
    assert transition.to is jobs.JobState.FAILED
    assert transition.error_code is jobs.ErrorCode.TOO_LARGE


async def test_corrupt_probe_is_invalid_media(tmp_path: Any) -> None:
    """Probe errors map to domain codes: a corrupt file is INVALID_MEDIA (permanent)."""
    media = _mod("transcribe_engine.application.ports.media")
    jobs = _mod("transcribe_engine.domain.jobs")
    _, _, storage, probe, normalizer, make_uow = await _world(
        b"RIFF-bad", probe_error=media.CorruptMediaError("bad")
    )
    transition = await _ingest(storage, probe, normalizer, make_uow, tmp_path)(_job())
    assert transition.to is jobs.JobState.FAILED
    assert transition.error_code is jobs.ErrorCode.INVALID_MEDIA


async def test_unsupported_probe_is_unsupported_format(tmp_path: Any) -> None:
    """A playlist or container refused by the probe maps to UNSUPPORTED_FORMAT."""
    media = _mod("transcribe_engine.application.ports.media")
    jobs = _mod("transcribe_engine.domain.jobs")
    _, _, storage, probe, normalizer, make_uow = await _world(
        b"#EXTM3U", probe_error=media.UnsupportedMediaError("playlist")
    )
    transition = await _ingest(storage, probe, normalizer, make_uow, tmp_path)(_job())
    assert transition.to is jobs.JobState.FAILED
    assert transition.error_code is jobs.ErrorCode.UNSUPPORTED_FORMAT


async def test_oversize_upload_is_refused_before_download(tmp_path: Any) -> None:
    """The head() size check refuses an object over the limit before any bytes are read."""
    jobs = _mod("transcribe_engine.domain.jobs")
    limits = _mod("transcribe_engine.domain.media_rules").IngestLimits(max_size_bytes=10)
    _, _, storage, probe, normalizer, make_uow = await _world(b"x" * 20)
    transition = await _ingest(storage, probe, normalizer, make_uow, tmp_path, limits=limits)(
        _job()
    )
    assert transition.error_code is jobs.ErrorCode.TOO_LARGE
    assert storage.stream_args == []
    assert probe.calls == []


async def test_retried_cache_hit_does_not_count_the_reference_twice(tmp_path: Any) -> None:
    """D-037. Running the same cache-hit job twice leaves one added reference, not two."""
    jobs = _mod("transcribe_engine.domain.jobs")
    keys = _mod("transcribe_engine.domain.keys")
    upload = b"RIFF-retry"
    store, _, storage, probe, normalizer, make_uow = await _world(upload)
    key = keys.result_key(hashlib.sha256(upload).hexdigest(), _config())
    store.results_by_key[key] = jobs.Result(
        id=key, result_key=key, media_id="old-media", config=_config(), ref_count=2
    )
    ingest = _ingest(storage, probe, normalizer, make_uow, tmp_path)
    assert (await ingest(_job())).to is jobs.JobState.COMPLETED
    assert (await ingest(_job())).to is jobs.JobState.COMPLETED
    assert store.results_by_key[key].ref_count == 3
