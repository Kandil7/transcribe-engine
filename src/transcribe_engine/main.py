"""Composition root: the only module allowed to import from every layer.

Wires Ports to Adapters. The API app (S08) and the worker handlers (S10) are built here; the worker
entry point in `worker.py` calls these builders and runs the loops.
"""

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import cast

import boto3
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.application.use_cases.ingest_job import IngestJob
from transcribe_engine.application.use_cases.prepare_chunks import PrepareChunks
from transcribe_engine.application.use_cases.process_job import ProcessJob
from transcribe_engine.domain.chunks import NORMALIZED_SAMPLE_RATE
from transcribe_engine.infrastructure.asr.plumbing import PlumbingASR
from transcribe_engine.infrastructure.clock import SystemClock
from transcribe_engine.infrastructure.db.uow import SqlUnitOfWork
from transcribe_engine.infrastructure.media.ffmpeg import FfmpegNormalizer
from transcribe_engine.infrastructure.media.ffprobe import FfprobeMediaProbe
from transcribe_engine.infrastructure.settings import Settings
from transcribe_engine.infrastructure.storage.s3 import S3ObjectStorage
from transcribe_engine.infrastructure.vad.whole_file import WholeFileVad
from transcribe_engine.presentation.api.app import create_app

__all__ = ["build_app", "build_handlers", "build_storage"]


def _uow(engine: AsyncEngine, tenant_id: str | None) -> AbstractAsyncContextManager[UnitOfWork]:
    # SqlUnitOfWork.__aenter__ returns Self, which mypy cannot match to the protocol's Self (D-036).
    # The adapter is the port's implementation; the cast only restates that for the checker.
    return cast(AbstractAsyncContextManager[UnitOfWork], SqlUnitOfWork(engine, tenant_id=tenant_id))


def build_app(engine: AsyncEngine, storage: ObjectStorage) -> FastAPI:
    def make_uow(tenant_id: str | None) -> AbstractAsyncContextManager[UnitOfWork]:
        return _uow(engine, tenant_id)

    return create_app(make_uow, storage, SystemClock())


def build_storage(settings: Settings) -> ObjectStorage:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    return S3ObjectStorage(client, settings.s3_bucket)


def build_handlers(
    engine: AsyncEngine, storage: ObjectStorage, settings: Settings
) -> tuple[IngestJob, ProcessJob]:
    """The cpu handler (ingest, then plan the chunks) and the gpu handler (process the chunks)."""

    def make_uow(tenant_id: str | None) -> AbstractAsyncContextManager[UnitOfWork]:
        return _uow(engine, tenant_id)

    scratch = Path(settings.scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    samples_per_ms = NORMALIZED_SAMPLE_RATE // 1000
    prepare = PrepareChunks(
        make_uow,
        WholeFileVad(storage),  # plumbing until S11 (D-035)
        max_samples=settings.chunk_max_ms * samples_per_ms,
        pad=settings.chunk_pad_ms * samples_per_ms,
    )
    ingest = IngestJob(
        make_uow=make_uow,
        storage=storage,
        probe=FfprobeMediaProbe(work_root=scratch),
        normalizer=FfmpegNormalizer(),
        scratch_root=scratch,
        prepare=prepare,
    )
    process = ProcessJob(
        make_uow,
        PlumbingASR(),  # plumbing until S12 (D-035)
        language="ar",
        concurrency=settings.asr_concurrency,
    )
    return ingest, process
