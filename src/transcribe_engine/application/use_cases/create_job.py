"""Create a transcription job (S08).

One transaction: the tenant row is locked, then the idempotency key, the limits, the media row,
the job (PENDING_VALIDATION on the cpu queue) and the idempotency record are written together.
A repeated Idempotency-Key returns the stored response; reusing it for another request is refused
(D-025, D-027).
"""

import hashlib
import json
import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from transcribe_engine.application.errors import (
    IdempotencyKeyReusedError,
    InvalidWebhookUrlError,
    QuotaExceededError,
    TooManyActiveJobsError,
    UnsupportedFeatureError,
    UnsupportedLanguageError,
    UploadNotFoundError,
)
from transcribe_engine.application.ports.clock import Clock
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.application.ports.tenancy import StoredResponse, TenantLimits
from transcribe_engine.domain.config import PipelineConfig
from transcribe_engine.domain.jobs import Job, JobState, Media
from transcribe_engine.domain.storage_keys import incoming_key

__all__ = ["CreateJobCommand", "CreateJobResult", "CreateTranscriptionJob"]

DEFAULT_ENGINE = "faster-whisper"  # D-001 local profile; the production engine is chosen in S12
DEFAULT_MODEL_REVISION = "pending-s00"  # S00 has not measured a revision yet (see REVIEW_QUEUE)
PIPELINE_VERSION = "1.0.0"
SUPPORTED_LANGUAGE = "ar"
DEFAULT_TENANT_LIMITS = (5, None)  # (max active jobs, quota in ms) when a tenant has no row


@dataclass(frozen=True)
class CreateJobCommand:
    tenant_id: str
    upload_id: str
    language: str
    engine: str | None
    diarization: bool
    webhook_url: str | None
    idempotency_key: str | None
    speakers: int | None = None


@dataclass(frozen=True)
class CreateJobResult:
    job_id: str
    status: int
    body: dict[str, Any]
    replayed: bool


MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]


class CreateTranscriptionJob:
    def __init__(self, make_uow: MakeUow, storage: ObjectStorage, clock: Clock) -> None:
        self._make_uow = make_uow
        self._storage = storage
        self._clock = clock

    async def __call__(self, cmd: CreateJobCommand) -> CreateJobResult:
        _validate(cmd)
        head = await self._storage.head(incoming_key(cmd.tenant_id, cmd.upload_id))
        if head is None:
            raise UploadNotFoundError
        request_hash = _request_hash(cmd)

        async with self._make_uow(cmd.tenant_id) as uow:
            await uow.tenants.lock(cmd.tenant_id)
            if cmd.idempotency_key is not None:
                stored = await uow.idempotency.get(cmd.tenant_id, cmd.idempotency_key)
                if stored is not None:
                    if stored.request_hash != request_hash:
                        raise IdempotencyKeyReusedError
                    return CreateJobResult(stored.job_id, stored.status, stored.body, replayed=True)
            await _check_limits(uow, cmd.tenant_id)

            await uow.media.upsert(
                Media(
                    id=cmd.upload_id,
                    tenant_id=cmd.tenant_id,
                    sha256=f"upload:{cmd.upload_id}",  # placeholder until S09 hashes (D-023)
                    storage_key=incoming_key(cmd.tenant_id, cmd.upload_id),
                    duration_ms=0,
                    format="unknown",
                    size_bytes=head.size,
                )
            )
            job = Job(
                id=secrets.token_hex(16),
                tenant_id=cmd.tenant_id,
                media_id=cmd.upload_id,
                state=JobState.PENDING_VALIDATION,
                stage=None,
                attempt_count=0,
                max_attempts=3,
                queue="cpu",
                config=_config(cmd.language, cmd.diarization, cmd.speakers),
                result_id=None,
                error_code=None,
                warnings=(),
                webhook_url=cmd.webhook_url,
            )
            await uow.jobs.add(job)
            body = _body(job)
            if cmd.idempotency_key is not None:
                await uow.idempotency.put(
                    cmd.tenant_id,
                    cmd.idempotency_key,
                    StoredResponse(job.id, 202, body, self._clock.now(), request_hash),
                )
            await uow.commit()
        return CreateJobResult(job.id, 202, body, replayed=False)


def _request_hash(cmd: CreateJobCommand) -> str:
    """The fields that define the job. The same Idempotency-Key with other fields is refused."""
    fields = {
        "upload_id": cmd.upload_id,
        "language": cmd.language,
        "engine": cmd.engine,
        "diarization": cmd.diarization,
        "webhook_url": cmd.webhook_url,
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def _validate(cmd: CreateJobCommand) -> None:
    if cmd.webhook_url is not None and not _is_https_url(cmd.webhook_url):
        raise InvalidWebhookUrlError  # D-048: https only; the address is checked at send time
    if cmd.language != SUPPORTED_LANGUAGE:
        raise UnsupportedLanguageError
    if cmd.engine not in (None, DEFAULT_ENGINE):
        raise UnsupportedFeatureError


def _is_https_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and bool(parts.hostname)


async def _check_limits(uow: UnitOfWork, tenant_id: str) -> None:
    limits = await uow.tenants.limits(tenant_id) or TenantLimits(tenant_id, *DEFAULT_TENANT_LIMITS)
    if await uow.tenants.count_active_jobs(tenant_id) >= limits.max_active_jobs:
        raise TooManyActiveJobsError
    quota = limits.quota_audio_ms
    if quota is not None and await uow.tenants.used_audio_ms(tenant_id) >= quota:
        raise QuotaExceededError


def _config(language: str, diarization: bool, speakers: int | None = None) -> PipelineConfig:
    return PipelineConfig(
        speakers=speakers,
        engine=DEFAULT_ENGINE,
        model_revision=DEFAULT_MODEL_REVISION,
        language=language,
        decoding_params={"temperature": 0},
        vad_params={},
        diarization_enabled=diarization,
        pipeline_version=PIPELINE_VERSION,
    )


def _body(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "state": job.state.value,
        "stage": None,
        "progress": job.progress,
        "warnings": list(job.warnings),
        "error_code": None,
    }
