"""SQLAlchemy Core repositories (S05). Each takes one connection inside a unit of work.

Conflicts are resolved in the database (ON CONFLICT), never by a read-then-write in Python.
Result ids are the result key itself, so they are deterministic (CLAUDE.md, D-019).
"""

import contextlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Row, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.config import PipelineConfig
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.jobs import (
    ErrorCode,
    Job,
    JobStage,
    JobState,
    Media,
    Result,
    Transition,
)
from transcribe_engine.domain.merge import MergedWords, RawWord, Word
from transcribe_engine.infrastructure.db.models import (
    chunk_result_table,
    chunk_table,
    jobs,
    media,
    results,
    transcript_table,
)

__all__ = ["SqlJobRepository", "SqlMediaRepository", "SqlResultRepository"]


def _config_from_canonical(text: str) -> PipelineConfig:
    """Rebuild the config from stored canonical text: a byte-exact round trip (D-019)."""
    data: dict[str, Any] = json.loads(text)
    return PipelineConfig(
        engine=data["engine"],
        model_revision=data["model_revision"],
        language=data["language"],
        decoding_params=data["decoding_params"],
        vad_params=data["vad_params"],
        diarization_enabled=data["diarization_enabled"],
        pipeline_version=data["pipeline_version"],
    )


def _config_jsonb(config: PipelineConfig) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(config.canonical_json())
    return loaded


def job_from_row(row: Row) -> Job:  # type: ignore[type-arg]
    """Map a jobs row to the domain Job. Shared by the repository and the queue (S06)."""
    return Job(
        id=row.id,
        tenant_id=row.tenant_id,
        media_id=row.media_id,
        state=JobState(row.state),
        stage=JobStage(row.stage) if row.stage else None,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        queue=row.queue,
        config=_config_from_canonical(row.config_canonical),
        result_id=row.result_id,
        error_code=ErrorCode(row.error_code) if row.error_code else None,
        warnings=tuple(row.warnings),
        priority=row.priority,
        run_after=row.run_after,
        progress=row.progress,
    )


class SqlMediaRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def upsert(self, value: Media) -> Media:
        """Dedupe is per tenant (D-019): another tenant's identical file is never returned."""
        await self._conn.execute(
            pg_insert(media)
            .values(
                id=value.id,
                tenant_id=value.tenant_id,
                sha256=value.sha256,
                storage_key=value.storage_key,
                duration_ms=value.duration_ms,
                format=value.format,
                size_bytes=value.size_bytes,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "sha256"])
        )
        row = (
            await self._conn.execute(
                select(media).where(
                    media.c.tenant_id == value.tenant_id, media.c.sha256 == value.sha256
                )
            )
        ).one()
        return Media(
            id=row.id,
            tenant_id=row.tenant_id,
            sha256=row.sha256,
            storage_key=row.storage_key,
            duration_ms=row.duration_ms,
            format=row.format,
            size_bytes=row.size_bytes,
        )

    async def finalize(
        self,
        media_id: str,
        tenant_id: str,
        sha256: str,
        duration_ms: int,
        format: str,
        size_bytes: int,
    ) -> Media:
        """D-029: fill the upload row, or return the tenant's existing row for this sha256.

        The update runs in a savepoint. If a concurrent upload with the same bytes inserts first,
        the unique constraint refuses the update and only the savepoint rolls back.
        """
        existing = (
            await self._conn.execute(
                select(media).where(media.c.tenant_id == tenant_id, media.c.sha256 == sha256)
            )
        ).one_or_none()
        if existing is None:
            with contextlib.suppress(IntegrityError):
                async with self._conn.begin_nested():
                    await self._conn.execute(
                        update(media)
                        .where(media.c.id == media_id, media.c.tenant_id == tenant_id)
                        .values(
                            sha256=sha256,
                            duration_ms=duration_ms,
                            format=format,
                            size_bytes=size_bytes,
                        )
                    )
            existing = (
                await self._conn.execute(
                    select(media).where(media.c.tenant_id == tenant_id, media.c.sha256 == sha256)
                )
            ).one()
        existing_row = existing
        return Media(
            id=existing_row.id,
            tenant_id=existing_row.tenant_id,
            sha256=existing_row.sha256,
            storage_key=existing_row.storage_key,
            duration_ms=existing_row.duration_ms,
            format=existing_row.format,
            size_bytes=existing_row.size_bytes,
        )


class SqlJobRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, job: Job) -> None:
        await self._conn.execute(
            insert(jobs).values(
                id=job.id,
                tenant_id=job.tenant_id,
                media_id=job.media_id,
                state=job.state.value,
                stage=job.stage.value if job.stage else None,
                queue=job.queue,
                attempt_count=job.attempt_count,
                max_attempts=job.max_attempts,
                result_id=job.result_id,
                error_code=job.error_code.value if job.error_code else None,
                warnings=list(job.warnings),
                pipeline_config=_config_jsonb(job.config),
                config_canonical=job.config.canonical_json(),
                priority=job.priority,
                run_after=job.run_after,
            )
        )

    async def get(self, tenant_id: str, job_id: str) -> Job | None:
        row = (
            await self._conn.execute(
                select(jobs).where(jobs.c.id == job_id, jobs.c.tenant_id == tenant_id)
            )
        ).one_or_none()
        return None if row is None else job_from_row(row)

    async def request_deletion(self, tenant_id: str, job_id: str, at: datetime) -> bool:
        result = await self._conn.execute(
            update(jobs)
            .where(jobs.c.id == job_id, jobs.c.tenant_id == tenant_id)
            .values(deletion_requested_at=at)
        )
        return bool(result.rowcount == 1)

    async def apply(
        self,
        job_id: str,
        t: Transition,
        *,
        expected: JobState,
        stage: JobStage | None = None,
        attempt_count: int | None = None,
    ) -> bool:
        """Compare-and-set: the row changes only while its state is still `expected` (D-017)."""
        values: dict[str, Any] = {
            "state": t.to.value,
            "error_code": t.error_code.value if t.error_code else None,
        }
        if stage is not None:
            values["stage"] = stage.value
        if attempt_count is not None:
            values["attempt_count"] = attempt_count
        result = await self._conn.execute(
            update(jobs).where(jobs.c.id == job_id, jobs.c.state == expected.value).values(**values)
        )
        return bool(result.rowcount == 1)


class SqlResultRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def claim_key(
        self, result_key: str, media_id: str, config: PipelineConfig
    ) -> tuple[Result, bool]:
        inserted = (
            await self._conn.execute(
                pg_insert(results)
                .values(
                    id=result_key,  # deterministic id (CLAUDE.md, D-019)
                    result_key=result_key,
                    media_id=media_id,
                    engine=config.engine,
                    model_revision=config.model_revision,
                    pipeline_version=config.pipeline_version,
                    pipeline_config=_config_jsonb(config),
                    config_canonical=config.canonical_json(),
                    ref_count=0,
                )
                # Any unique key: result_key or the deterministic id (D-019).
                .on_conflict_do_nothing()
                .returning(results.c.id)
            )
        ).one_or_none()
        if inserted is not None:
            created = Result(
                id=result_key, result_key=result_key, media_id=media_id, config=config, ref_count=0
            )
            return created, True
        existing = await self.get_by_key(result_key)
        if existing is None:  # the creator committed the conflicting row before we read it
            raise PermanentError("result key conflict without a visible row")
        return existing, False

    async def get_by_key(self, result_key: str) -> Result | None:
        row = (
            await self._conn.execute(select(results).where(results.c.result_key == result_key))
        ).one_or_none()
        if row is None:
            return None
        return Result(
            id=row.id,
            result_key=row.result_key,
            media_id=row.media_id,
            config=_config_from_canonical(row.config_canonical),
            ref_count=row.ref_count,
        )

    async def incr_ref(self, result_id: str, delta: int) -> int:
        """Refuse an unknown id or a count that would go negative (D-019)."""
        row = (
            await self._conn.execute(
                update(results)
                .where(results.c.id == result_id, results.c.ref_count + delta >= 0)
                .values(ref_count=results.c.ref_count + delta)
                .returning(results.c.ref_count)
            )
        ).one_or_none()
        if row is None:
            raise PermanentError("result reference change refused")
        return int(row.ref_count)


class SqlChunkRepository:
    """Plan, results and transcript for S10 (migration 0005). Tenant scope comes from RLS and from
    every query's tenant_id filter."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add_plan(self, tenant_id: str, job_id: str, chunks: Sequence[Chunk]) -> None:
        for chunk in chunks:
            await self._conn.execute(
                pg_insert(chunk_table)
                .values(
                    chunk_id=chunk.chunk_id,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    idx=chunk.idx,
                    total=chunk.total,
                    start_sample=chunk.start_sample,
                    end_sample=chunk.end_sample,
                    pad_before=chunk.pad_before,
                    pad_after=chunk.pad_after,
                    sample_rate=chunk.sample_rate,
                    media_sha256=chunk.media_sha256,
                    config_hash=chunk.config_hash,
                )
                .on_conflict_do_nothing(index_elements=["chunk_id"])
            )

    async def plan(self, tenant_id: str, job_id: str) -> tuple[Chunk, ...]:
        rows = (
            await self._conn.execute(
                select(chunk_table)
                .where(chunk_table.c.tenant_id == tenant_id, chunk_table.c.job_id == job_id)
                .order_by(chunk_table.c.idx)
            )
        ).all()
        return tuple(
            Chunk(
                chunk_id=row.chunk_id,
                job_id=row.job_id,
                idx=row.idx,
                total=row.total,
                start_sample=row.start_sample,
                end_sample=row.end_sample,
                pad_before=row.pad_before,
                pad_after=row.pad_after,
                sample_rate=row.sample_rate,
                media_sha256=row.media_sha256,
                config_hash=row.config_hash,
            )
            for row in rows
        )

    async def save_result(
        self, tenant_id: str, job_id: str, chunk_id: str, words: tuple[RawWord, ...]
    ) -> None:
        payload = [
            {"text": w.text, "local_start": w.local_start, "local_end": w.local_end, "conf": w.conf}
            for w in words
        ]
        await self._conn.execute(
            pg_insert(chunk_result_table)
            .values(chunk_id=chunk_id, tenant_id=tenant_id, job_id=job_id, words=payload)
            .on_conflict_do_update(index_elements=["chunk_id"], set_={"words": payload})
        )

    async def results(self, tenant_id: str, job_id: str) -> dict[str, tuple[RawWord, ...]]:
        rows = (
            await self._conn.execute(
                select(chunk_result_table.c.chunk_id, chunk_result_table.c.words).where(
                    chunk_result_table.c.tenant_id == tenant_id,
                    chunk_result_table.c.job_id == job_id,
                )
            )
        ).all()
        return {
            row.chunk_id: tuple(
                RawWord(w["text"], w["local_start"], w["local_end"], w["conf"]) for w in row.words
            )
            for row in rows
        }

    async def save_transcript(self, tenant_id: str, job_id: str, merged: MergedWords) -> None:
        payload = [
            {
                "text": w.text,
                "start_ms": w.start_ms,
                "end_ms": w.end_ms,
                "conf": w.conf,
                "chunk_idx": w.chunk_idx,
            }
            for w in merged.words
        ]
        await self._conn.execute(
            pg_insert(transcript_table)
            .values(
                job_id=job_id,
                tenant_id=tenant_id,
                sample_rate=merged.sample_rate,
                words=payload,
            )
            .on_conflict_do_update(
                index_elements=["job_id"],
                set_={"sample_rate": merged.sample_rate, "words": payload},
            )
        )

    async def transcript(self, tenant_id: str, job_id: str) -> MergedWords | None:
        row = (
            await self._conn.execute(
                select(transcript_table).where(
                    transcript_table.c.tenant_id == tenant_id,
                    transcript_table.c.job_id == job_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return MergedWords(
            words=tuple(
                Word(
                    text=w["text"],
                    start_ms=w["start_ms"],
                    end_ms=w["end_ms"],
                    conf=w["conf"],
                    chunk_idx=w["chunk_idx"],
                )
                for w in row.words
            ),
            sample_rate=row.sample_rate,
        )
