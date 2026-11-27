"""SQL store for versioned transcripts (S22, design: التمثيل المرجعي).

Every version is one row in transcript_revisions with its canonical JSON (the domain serializes it,
so the stored text round-trips exactly). Version 1 is the ASR version: it is built from the job's
merged words on the first read, and then stored like any other version.

Optimistic concurrency: the primary key (transcript_id, version) refuses a second row with the same
version. That refusal becomes StaleVersionError, so two editors that both start from the same base
version cannot both save (AC-3).
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from transcribe_engine.application.errors import StaleVersionError
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.domain.transcript import (
    CanonicalTranscript,
    Provenance,
    from_json,
    to_json,
    transcript_from_merged,
)

__all__ = ["SqlTranscriptVersions"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]

_LATEST = text(
    "SELECT canonical FROM transcript_revisions WHERE transcript_id = :tid "
    "ORDER BY version DESC LIMIT 1"
)
_INSERT = text(
    "INSERT INTO transcript_revisions (transcript_id, tenant_id, version, source, canonical) "
    "VALUES (:tid, :tenant, :version, :source, :canonical)"
)


class SqlTranscriptVersions:
    def __init__(self, engine: AsyncEngine, make_uow: MakeUow) -> None:
        self._engine = engine
        self._make_uow = make_uow

    async def latest(self, tenant_id: str, transcript_id: str) -> CanonicalTranscript | None:
        stored = await self._latest_text(tenant_id, transcript_id)
        if stored is not None:
            return from_json(stored.encode("utf-8"))
        base = await self._asr_version(tenant_id, transcript_id)
        if base is None:
            return None
        try:
            await self.save(tenant_id, base)
        except StaleVersionError:
            # Another request stored version 1 first; read what it stored.
            stored = await self._latest_text(tenant_id, transcript_id)
            return from_json(stored.encode("utf-8")) if stored is not None else None
        return base

    async def save(self, tenant_id: str, transcript: CanonicalTranscript) -> None:
        canonical = to_json(transcript).decode("utf-8")
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id}
                )
                await conn.execute(
                    _INSERT,
                    {
                        "tid": transcript.transcript_id,
                        "tenant": tenant_id,
                        "version": transcript.version,
                        "source": transcript.source,
                        "canonical": canonical,
                    },
                )
        except IntegrityError as exc:
            raise StaleVersionError from exc

    async def _latest_text(self, tenant_id: str, transcript_id: str) -> str | None:
        async with self._engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id}
            )
            return (await conn.execute(_LATEST, {"tid": transcript_id})).scalar_one_or_none()

    async def _asr_version(self, tenant_id: str, job_id: str) -> CanonicalTranscript | None:
        """Version 1 from the job's merged words. None when the job or its transcript is missing."""
        async with self._make_uow(tenant_id) as uow:
            job = await uow.jobs.get(tenant_id, job_id)
            if job is None:
                return None
            merged = await uow.chunks.transcript(tenant_id, job_id)
        if merged is None:
            return None
        config = job.config
        return transcript_from_merged(
            merged,
            transcript_id=job_id,
            media_id=job.media_id,
            language=config.language,
            provenance=Provenance(
                engine=config.engine,
                revision=config.model_revision,
                pipeline_version=config.pipeline_version,
                config_hash=config.config_hash(),
            ),
        )
