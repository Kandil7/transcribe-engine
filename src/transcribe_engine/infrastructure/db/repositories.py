"""SQLAlchemy Core repositories (S05). Each takes one connection inside a unit of work.

Conflicts are resolved in the database (ON CONFLICT), never by a read-then-write in Python.
"""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from transcribe_engine.domain.config import PipelineConfig
from transcribe_engine.domain.jobs import (
    ErrorCode,
    Job,
    JobStage,
    JobState,
    Media,
    Result,
    Transition,
)
from transcribe_engine.infrastructure.db.models import jobs, media, results

__all__ = ["SqlJobRepository", "SqlMediaRepository", "SqlResultRepository"]


def _config_to_json(config: PipelineConfig) -> dict[str, Any]:
    """The canonical JSON form is the stored form, so the round trip is byte-equal (AC-5)."""
    loaded: dict[str, Any] = json.loads(config.canonical_json())
    return loaded


def _config_from_json(data: dict[str, Any]) -> PipelineConfig:
    return PipelineConfig(
        engine=data["engine"],
        model_revision=data["model_revision"],
        language=data["language"],
        decoding_params=data["decoding_params"],
        vad_params=data["vad_params"],
        diarization_enabled=data["diarization_enabled"],
        pipeline_version=data["pipeline_version"],
    )


class SqlMediaRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def upsert(self, value: Media) -> Media:
        await self._conn.execute(
            pg_insert(media)
            .values(
                id=value.id,
                sha256=value.sha256,
                storage_key=value.storage_key,
                duration_ms=value.duration_ms,
                format=value.format,
                size_bytes=value.size_bytes,
            )
            .on_conflict_do_nothing(index_elements=["sha256"])
        )
        row = (await self._conn.execute(select(media).where(media.c.sha256 == value.sha256))).one()
        return Media(
            id=row.id,
            sha256=row.sha256,
            storage_key=row.storage_key,
            duration_ms=row.duration_ms,
            format=row.format,
            size_bytes=row.size_bytes,
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
                pipeline_config=_config_to_json(job.config),
            )
        )

    async def get(self, tenant_id: str, job_id: str) -> Job | None:
        row = (
            await self._conn.execute(
                select(jobs).where(jobs.c.id == job_id, jobs.c.tenant_id == tenant_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return Job(
            id=row.id,
            tenant_id=row.tenant_id,
            media_id=row.media_id,
            state=JobState(row.state),
            stage=JobStage(row.stage) if row.stage else None,
            attempt_count=row.attempt_count,
            max_attempts=row.max_attempts,
            queue=row.queue,
            config=_config_from_json(row.pipeline_config),
            result_id=row.result_id,
            error_code=ErrorCode(row.error_code) if row.error_code else None,
            warnings=tuple(row.warnings),
        )

    async def apply(
        self, job_id: str, t: Transition, *, expected: JobState, stage: JobStage | None = None
    ) -> bool:
        """Compare-and-set: the row changes only while its state is still `expected` (D-017)."""
        values: dict[str, Any] = {
            "state": t.to.value,
            "error_code": t.error_code.value if t.error_code else None,
        }
        if stage is not None:
            values["stage"] = stage.value
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
        new_id = uuid4().hex
        inserted = (
            await self._conn.execute(
                pg_insert(results)
                .values(
                    id=new_id,
                    result_key=result_key,
                    media_id=media_id,
                    engine=config.engine,
                    model_revision=config.model_revision,
                    pipeline_version=config.pipeline_version,
                    pipeline_config=_config_to_json(config),
                    ref_count=0,
                )
                .on_conflict_do_nothing(index_elements=["result_key"])
                .returning(results.c.id)
            )
        ).one_or_none()
        if inserted is not None:
            created = Result(
                id=new_id, result_key=result_key, media_id=media_id, config=config, ref_count=0
            )
            return created, True
        existing = await self.get_by_key(result_key)
        if existing is None:  # the conflicting row is committed by the creator before we read it
            raise RuntimeError("result key conflict without a visible row")
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
            config=_config_from_json(row.pipeline_config),
            ref_count=row.ref_count,
        )

    async def incr_ref(self, result_id: str, delta: int) -> int:
        row = (
            await self._conn.execute(
                update(results)
                .where(results.c.id == result_id)
                .values(ref_count=results.c.ref_count + delta)
                .returning(results.c.ref_count)
            )
        ).one()
        return int(row.ref_count)
