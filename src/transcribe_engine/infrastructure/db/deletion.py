"""SQL deletion store (S21, D-059), run on the unit-of-work connection.

- A job's rows go: result references (each decrements the result's ref_count), chunk results,
  chunks, the merged transcript, idempotency keys, then the job row.
- A result (and its versions and segments) is removed only when ref_count is 0 and no job still
  points at it. A media row (the original upload) is removed only when no job and no result uses
  it.
- The audit row keeps counts and flags only (AC-3)."""

import json
from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from transcribe_engine.application.ports.deletion import DeletionOutcome
from transcribe_engine.domain.storage_keys import job_prefix

__all__ = ["SqlDeletionStore"]

_NOT_FOUND = DeletionOutcome(
    found=False, rows_deleted={}, result_released=False, media_released=False, storage_keys=()
)


class SqlDeletionStore:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def delete_job(self, tenant_id: str, job_id: str) -> DeletionOutcome:
        job = (
            await self._conn.execute(
                text(
                    "SELECT media_id, result_id FROM jobs WHERE id = :job AND tenant_id = :tenant"
                ),
                {"job": job_id, "tenant": tenant_id},
            )
        ).one_or_none()
        if job is None:
            return _NOT_FOUND
        rows: dict[str, int] = {}
        refs = (
            await self._conn.execute(
                text("SELECT result_id FROM result_refs WHERE job_id = :job"), {"job": job_id}
            )
        ).all()
        for ref in refs:
            await self._conn.execute(
                text(
                    "UPDATE results SET ref_count = ref_count - 1 WHERE id = :id AND ref_count > 0"
                ),
                {"id": ref.result_id},
            )
        rows["result_refs"] = await self._delete("result_refs", job_id)
        rows["chunk_results"] = await self._delete("chunk_results", job_id)
        rows["chunks"] = await self._delete("chunks", job_id)
        rows["transcripts"] = await self._delete("transcripts", job_id)
        rows["idempotency_keys"] = await self._delete("idempotency_keys", job_id)
        rows["jobs"] = await self._delete("jobs", job_id)

        result_released = False
        if job.result_id is not None:
            result_released = await self._release_result(job.result_id, rows)
        media_released = await self._release_media(tenant_id, job.media_id, rows)
        keys = [job_prefix(tenant_id, job_id)]
        if media_released:
            keys.append(media_released)
        return DeletionOutcome(
            found=True,
            rows_deleted={name: count for name, count in rows.items() if count},
            result_released=result_released,
            media_released=bool(media_released),
            storage_keys=tuple(keys),
        )

    async def record_audit(
        self,
        tenant_id: str,
        event: str,
        subject_id: str,
        at: datetime,
        detail: Mapping[str, object],
    ) -> None:
        await self._conn.execute(
            text(
                "INSERT INTO audit_log (tenant_id, event, subject_id, at, detail) "
                "VALUES (:tenant, :event, :subject, :at, CAST(:detail AS jsonb))"
            ),
            {
                "tenant": tenant_id,
                "event": event,
                "subject": subject_id,
                "at": at,
                "detail": json.dumps(dict(detail), sort_keys=True),
            },
        )

    async def requested_deletions(self) -> tuple[tuple[str, str], ...]:
        rows = (
            await self._conn.execute(
                text(
                    "SELECT tenant_id AS tenant, id AS job FROM jobs "
                    "WHERE deletion_requested_at IS NOT NULL ORDER BY id"
                )
            )
        ).all()
        return tuple((row.tenant, row.job) for row in rows)

    async def expired_audio(self, now: datetime) -> tuple[tuple[str, str], ...]:
        rows = (
            await self._conn.execute(
                text(
                    "SELECT j.tenant_id AS tenant, j.id AS job FROM jobs j "
                    "LEFT JOIN tenants t ON t.id = j.tenant_id "
                    "WHERE j.audio_deleted_at IS NULL AND j.deletion_requested_at IS NULL "
                    "AND j.state IN ('COMPLETED', 'FAILED', 'CANCELLED') "
                    "AND j.created_at < CAST(:now AS timestamptz) "
                    "- make_interval(days => COALESCE(t.retention_days, 30)) "
                    "ORDER BY j.id"
                ),
                {"now": now},
            )
        ).all()
        return tuple((row.tenant, row.job) for row in rows)

    async def expire_audio(self, tenant_id: str, job_id: str, now: datetime) -> tuple[str, ...]:
        job = (
            await self._conn.execute(
                text("SELECT media_id FROM jobs WHERE id = :job AND tenant_id = :tenant"),
                {"job": job_id, "tenant": tenant_id},
            )
        ).one_or_none()
        if job is None:
            return ()
        await self._conn.execute(
            text("UPDATE jobs SET audio_deleted_at = :now WHERE id = :job"),
            {"now": now, "job": job_id},
        )
        keys = [job_prefix(tenant_id, job_id)]
        shared = (
            await self._conn.execute(
                text(
                    "SELECT count(*) FROM jobs WHERE media_id = :media AND id <> :job "
                    "AND audio_deleted_at IS NULL"
                ),
                {"media": job.media_id, "job": job_id},
            )
        ).scalar_one()
        if shared == 0:
            storage_key = (
                await self._conn.execute(
                    text("SELECT storage_key FROM media WHERE id = :media"), {"media": job.media_id}
                )
            ).scalar_one_or_none()
            if storage_key is not None:
                keys.append(storage_key)
        return tuple(keys)

    async def _delete(self, table: str, job_id: str) -> int:
        # The table names are fixed in this module, never taken from a caller.
        statement = {
            "result_refs": "DELETE FROM result_refs WHERE job_id = :job",
            "chunk_results": "DELETE FROM chunk_results WHERE job_id = :job",
            "chunks": "DELETE FROM chunks WHERE job_id = :job",
            "transcripts": "DELETE FROM transcripts WHERE job_id = :job",
            "idempotency_keys": "DELETE FROM idempotency_keys WHERE job_id = :job",
            "jobs": "DELETE FROM jobs WHERE id = :job",
        }[table]
        result = await self._conn.execute(text(statement), {"job": job_id})
        return int(result.rowcount)

    async def _release_result(self, result_id: str, rows: dict[str, int]) -> bool:
        still_used = (
            await self._conn.execute(
                text("SELECT count(*) FROM jobs WHERE result_id = :id"), {"id": result_id}
            )
        ).scalar_one()
        refs = (
            await self._conn.execute(
                text("SELECT ref_count FROM results WHERE id = :id"), {"id": result_id}
            )
        ).scalar_one_or_none()
        if refs is None or still_used or refs:
            return False
        version_ids = (
            (
                await self._conn.execute(
                    text("SELECT id FROM transcript_versions WHERE result_id = :id"),
                    {"id": result_id},
                )
            )
            .scalars()
            .all()
        )
        if version_ids:
            seg = await self._conn.execute(
                text("DELETE FROM segments WHERE version_id = ANY(:ids)"),
                {"ids": list(version_ids)},
            )
            rows["segments"] = int(seg.rowcount)
            ver = await self._conn.execute(
                text("DELETE FROM transcript_versions WHERE result_id = :id"), {"id": result_id}
            )
            rows["transcript_versions"] = int(ver.rowcount)
        await self._conn.execute(
            text("DELETE FROM result_refs WHERE result_id = :id"), {"id": result_id}
        )
        await self._conn.execute(text("DELETE FROM results WHERE id = :id"), {"id": result_id})
        rows["results"] = 1
        return True

    async def _release_media(
        self, tenant_id: str, media_id: str, rows: dict[str, int]
    ) -> str | None:
        """The media's storage key if the row was removed, else None."""
        used = (
            await self._conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM jobs WHERE media_id = :media) "
                    "+ (SELECT count(*) FROM results WHERE media_id = :media)"
                ),
                {"media": media_id},
            )
        ).scalar_one()
        if used:
            return None
        key = (
            await self._conn.execute(
                text("SELECT storage_key FROM media WHERE id = :media AND tenant_id = :tenant"),
                {"media": media_id, "tenant": tenant_id},
            )
        ).scalar_one_or_none()
        if key is None:
            return None
        await self._conn.execute(text("DELETE FROM media WHERE id = :media"), {"media": media_id})
        rows["media"] = 1
        return str(key)
