"""Composition root: the only module allowed to import from every layer.

Wires Ports to Adapters. The API app (S08) and the worker handlers (S10) are built here; the worker
entry point in `worker.py` calls these builders and runs the loops.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import cast

import boto3
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from transcribe_engine.application.ports.asr import ASREngine
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.search import Embedder
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.application.ports.versions import SegmentAligner
from transcribe_engine.application.use_cases.ingest_job import IngestJob
from transcribe_engine.application.use_cases.prepare_chunks import PrepareChunks
from transcribe_engine.application.use_cases.process_job import ProcessJob
from transcribe_engine.application.use_cases.publish_outbox import OutboxPublisher
from transcribe_engine.application.use_cases.save_correction import SaveCorrection
from transcribe_engine.domain.chunks import NORMALIZED_SAMPLE_RATE
from transcribe_engine.infrastructure.alignment.load import load_wav2vec2_aligner
from transcribe_engine.infrastructure.alignment.unavailable import UnavailableAligner
from transcribe_engine.infrastructure.asr.cohere_local import CohereLocalASR
from transcribe_engine.infrastructure.asr.plumbing import PlumbingASR
from transcribe_engine.infrastructure.asr.vllm_client import VllmASR, VllmClient
from transcribe_engine.infrastructure.asr.whisper_local import WhisperLocalASR
from transcribe_engine.infrastructure.clock import SystemClock
from transcribe_engine.infrastructure.db.outbox import SqlOutboxStore, SqlWebhookSecrets
from transcribe_engine.infrastructure.db.uow import SqlUnitOfWork
from transcribe_engine.infrastructure.db.versions import SqlTranscriptVersions
from transcribe_engine.infrastructure.http.webhook_sender import DnsResolver, HttpWebhookSender
from transcribe_engine.infrastructure.media.ffmpeg import FfmpegNormalizer
from transcribe_engine.infrastructure.media.ffprobe import FfprobeMediaProbe
from transcribe_engine.infrastructure.ml.silero_vad import SileroVad
from transcribe_engine.infrastructure.observability.tracing import LogTracer
from transcribe_engine.infrastructure.search.pg_index import SqlSearchIndex
from transcribe_engine.infrastructure.settings import Settings
from transcribe_engine.infrastructure.storage.s3 import S3ObjectStorage
from transcribe_engine.presentation.api.app import create_app
from transcribe_engine.presentation.api.routes_search import SearchServices

__all__ = ["build_app", "build_handlers", "build_make_uow", "build_publisher", "build_storage"]


def _uow(engine: AsyncEngine, tenant_id: str | None) -> AbstractAsyncContextManager[UnitOfWork]:
    # SqlUnitOfWork.__aenter__ returns Self, which mypy cannot match to the protocol's Self (D-036).
    # The adapter is the port's implementation; the cast only restates that for the checker.
    return cast(AbstractAsyncContextManager[UnitOfWork], SqlUnitOfWork(engine, tenant_id=tenant_id))


def build_app(
    engine: AsyncEngine,
    storage: ObjectStorage,
    aligner: SegmentAligner | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    """The API. `aligner` is None on deployments without an aligner.

    Edits that need new word times are then refused with 503 (S22, R-005). `embedder` is None on
    deployments without the search model; the search routes then answer 503 (S18, D-079)."""

    def make_uow(tenant_id: str | None) -> AbstractAsyncContextManager[UnitOfWork]:
        return _uow(engine, tenant_id)

    versions = SqlTranscriptVersions(engine, make_uow)
    save = SaveCorrection(versions, aligner or UnavailableAligner())
    search = (
        SearchServices(embedder=embedder, index=SqlSearchIndex(engine), versions=versions)
        if embedder is not None
        else None
    )
    return create_app(
        make_uow, storage, SystemClock(), save_correction=save.__call__, search=search
    )


def build_make_uow(
    engine: AsyncEngine,
) -> Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]:
    """The unit-of-work factory for the worker processes (S21 sweeper, S20 publisher)."""

    def make_uow(tenant_id: str | None) -> AbstractAsyncContextManager[UnitOfWork]:
        return _uow(engine, tenant_id)

    return make_uow


def build_publisher(
    engine: AsyncEngine, owner: str, sender: HttpWebhookSender, secret_key: bytes | None
) -> OutboxPublisher:
    """The webhook publisher (S20): outbox rows to signed HTTPS deliveries, with the SSRF check.
    `owner` names this process in the outbox leases (D-053). The caller owns `sender`
    and closes it."""
    return OutboxPublisher(
        SqlOutboxStore(engine),
        SqlWebhookSecrets(engine, key=secret_key),
        sender,
        SystemClock(),
        DnsResolver(),
        owner,
    )


def build_storage(settings: Settings) -> ObjectStorage:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    return S3ObjectStorage(client, settings.s3_bucket)


def _asr_engine(storage: ObjectStorage, settings: Settings, *, load: bool) -> ASREngine:
    """The configured ASR engine (D-063).

    The plumbing engine returns no words; use it only to test the pipeline itself (D-035)."""
    if settings.asr_engine == "plumbing":
        return PlumbingASR()
    if settings.asr_engine == "cohere_local":
        # Local Cohere model: text from the model, word times from the aligner (D-074, D-070).
        aligner = (
            load_wav2vec2_aligner(storage, settings.aligner_model_id, settings.aligner_revision)
            if load
            else None
        )
        cohere = CohereLocalASR(storage, device=settings.asr_device, aligner=aligner)
        if load:  # only the GPU worker runs chunks; a broken model stops it at startup
            cohere.load()
        return cohere
    if settings.asr_engine == "vllm":
        client = VllmClient(settings.vllm_url, settings.vllm_model)
        # The aligner places text that has no word times (D-067, D-070).
        # Only the GPU worker loads it.
        aligner = (
            load_wav2vec2_aligner(storage, settings.aligner_model_id, settings.aligner_revision)
            if load
            else None
        )
        return VllmASR(storage, client, aligner=aligner)
    if settings.asr_engine == "whisper_local":
        engine = WhisperLocalASR(
            storage, model_id=settings.asr_model_id, device=settings.asr_device
        )
        if load:  # only the GPU worker runs chunks; a broken model stops it at startup (review)
            engine.load()
        return engine
    raise ValueError(f"unknown TE_ASR_ENGINE: {settings.asr_engine}")


def build_handlers(
    engine: AsyncEngine, storage: ObjectStorage, settings: Settings, *, load_asr: bool
) -> tuple[IngestJob, ProcessJob]:
    """The cpu handler (ingest, then plan the chunks) and the gpu handler (process the chunks)."""

    def make_uow(tenant_id: str | None) -> AbstractAsyncContextManager[UnitOfWork]:
        return _uow(engine, tenant_id)

    scratch = Path(settings.scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    tracer = LogTracer()
    samples_per_ms = NORMALIZED_SAMPLE_RATE // 1000
    prepare = PrepareChunks(
        make_uow,
        SileroVad(storage, scratch),
        max_samples=settings.chunk_max_ms * samples_per_ms,  # the engine's longest chunk (S11)
        pad=settings.chunk_pad_ms * samples_per_ms,
        overlap_samples=settings.chunk_overlap_ms * samples_per_ms,
        tracer=tracer,
    )
    ingest = IngestJob(
        make_uow=make_uow,
        storage=storage,
        probe=FfprobeMediaProbe(work_root=scratch),
        normalizer=FfmpegNormalizer(),
        scratch_root=scratch,
        prepare=prepare,
        tracer=tracer,
    )
    process = ProcessJob(
        make_uow,
        _asr_engine(storage, settings, load=load_asr),
        language="ar",
        concurrency=settings.asr_concurrency,
        # A chunk the model cannot read fails the job, not a silent transcript with a gap (review).
        require_complete_text=settings.asr_engine in ("whisper_local", "cohere_local", "vllm"),
        tracer=tracer,
    )
    return ingest, process
