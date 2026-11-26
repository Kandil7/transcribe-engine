"""S10 end to end on fakes (AC-6): upload → ingest (with chunk planning) → ProcessJob → COMPLETED.

Storage, repositories, VAD, ASR and the media tools are fakes, so this runs without Docker. The
Postgres path is covered by the repository contract tests. Imports happen inside helpers.
"""

import hashlib
import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.integration

RATE = 16_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def test_upload_to_completed(tmp_path: Path) -> None:
    fakes_repo = _mod("tests.fakes.repositories")
    fakes_storage = _mod("tests.fakes.storage")
    fakes_media = _mod("tests.fakes.media")
    fakes_vad = _mod("tests.fakes.vad")
    fakes_asr = _mod("tests.fakes.asr")
    media = _mod("transcribe_engine.application.ports.media")
    vad_port = _mod("transcribe_engine.application.ports.vad")
    chunks_mod = _mod("transcribe_engine.domain.chunks")
    merge = _mod("transcribe_engine.domain.merge")
    jobs_mod = _mod("transcribe_engine.domain.jobs")
    config_mod = _mod("transcribe_engine.domain.config")
    ingest_mod = _mod("transcribe_engine.application.use_cases.ingest_job")
    prepare_mod = _mod("transcribe_engine.application.use_cases.prepare_chunks")
    process_mod = _mod("transcribe_engine.application.use_cases.process_job")

    upload = b"RIFF-upload-bytes"
    upload_sha = hashlib.sha256(upload).hexdigest()
    config = config_mod.PipelineConfig(
        engine="faster-whisper",
        model_revision="pending-s00",
        language="ar",
        decoding_params={"temperature": 0.0},
        vad_params={},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )
    job: Any = jobs_mod.Job(
        id="job-e2e",
        tenant_id="tenant-a",
        media_id="upload-e2e",
        state=jobs_mod.JobState.PENDING_VALIDATION,
        stage=None,
        attempt_count=1,
        max_attempts=3,
        queue="cpu",
        config=config,
        result_id=None,
        error_code=None,
        warnings=(),
    )

    store = fakes_repo.FakeStore()
    store.media_by_tenant_sha[("tenant-a", "upload:upload-e2e")] = jobs_mod.Media(
        id="upload-e2e",
        tenant_id="tenant-a",
        sha256="upload:upload-e2e",
        storage_key="incoming/tenant-a/upload-e2e",
        duration_ms=0,
        format="unknown",
        size_bytes=len(upload),
    )
    storage = fakes_storage.FakeObjectStorage()
    await storage.put("incoming/tenant-a/upload-e2e", upload)

    def make_uow(tenant_id: str | None = None) -> Any:
        return fakes_repo.FakeUnitOfWork(store)

    regions = (chunks_mod.SpeechRegion(0, RATE), chunks_mod.SpeechRegion(RATE, 2 * RATE))
    vad = fakes_vad.FakeVad(vad_port.VadResult(total_samples=2 * RATE, regions=regions))
    prepare = prepare_mod.PrepareChunks(make_uow, vad, max_samples=RATE, pad=0)
    probe = fakes_media.FakeMediaProbe(info=media.MediaInfo("mp3", 2_000, 44_100, 2, len(upload)))
    normalizer = fakes_media.FakeAudioNormalizer(
        output=media.NormalizedAudio(2_000, RATE, 1, 64_000)
    )
    ingest = ingest_mod.IngestJob(
        make_uow=make_uow,
        storage=storage,
        probe=probe,
        normalizer=normalizer,
        scratch_root=tmp_path,
        prepare=prepare,
    )
    assert (await ingest(job)).to is jobs_mod.JobState.QUEUED

    planned = chunks_mod.plan_chunks(
        list(regions),
        max_samples=RATE,
        pad=0,
        total_samples=2 * RATE,
        sample_rate=RATE,
        media_sha256=upload_sha,
        config_hash=config.config_hash(),
        job_id=job.id,
    )
    script = {
        chunk.chunk_id: (merge.RawWord(f"w{chunk.idx}", 100, 2_000, None),) for chunk in planned
    }
    asr = fakes_asr.FakeASR(script=script)
    process = process_mod.ProcessJob(make_uow, asr)
    job = jobs_mod.Job(**{**job.__dict__, "state": jobs_mod.JobState.PROCESSING, "queue": "gpu"})
    result = await process(job)
    assert result.to is jobs_mod.JobState.COMPLETED
    async with make_uow("tenant-a") as uow:
        transcript = await uow.chunks.transcript("tenant-a", job.id)
    assert [w.text for w in transcript.words] == ["w0", "w1"]
