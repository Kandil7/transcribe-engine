"""SQL repositories for API keys, tenant limits and idempotency (S08, D-025, D-026).

api_keys, tenants and idempotency_keys carry no RLS: reads take an explicit tenant id, or
(for key lookup) run before any tenant is known.
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.application.ports.tenancy import StoredResponse, TenantLimits

__all__ = ["SqlApiKeyRepository", "SqlIdempotencyRepository", "SqlTenantRepository"]

_ACTIVE_STATES = ["QUEUED", "PENDING_VALIDATION", "PROCESSING", "RETRY_SCHEDULED"]


class SqlApiKeyRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def find_by_hash(self, key_hash: str) -> ApiPrincipal | None:
        row = (
            await self._conn.execute(
                text(
                    "SELECT id, tenant_id, scopes FROM api_keys "
                    "WHERE key_hash = :hash AND revoked_at IS NULL"
                ),
                {"hash": key_hash},
            )
        ).one_or_none()
        if row is None:
            return None
        return ApiPrincipal(tenant_id=row.tenant_id, key_id=row.id, scopes=frozenset(row.scopes))


class SqlTenantRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def limits(self, tenant_id: str) -> TenantLimits | None:
        row = (
            await self._conn.execute(
                text("SELECT id, max_active_jobs, quota_audio_ms FROM tenants WHERE id = :id"),
                {"id": tenant_id},
            )
        ).one_or_none()
        if row is None:
            return None
        return TenantLimits(
            tenant_id=row.id,
            max_active_jobs=row.max_active_jobs,
            quota_audio_ms=row.quota_audio_ms,
        )

    async def count_active_jobs(self, tenant_id: str) -> int:
        result = await self._conn.execute(
            text(
                "SELECT count(*) FROM jobs WHERE tenant_id = :t "
                "AND state = ANY(CAST(:states AS text[]))"
            ),
            {"t": tenant_id, "states": _ACTIVE_STATES},
        )
        return int(result.scalar_one())

    async def used_audio_ms(self, tenant_id: str) -> int:
        result = await self._conn.execute(
            text("SELECT coalesce(sum(duration_ms), 0) FROM media WHERE tenant_id = :t"),
            {"t": tenant_id},
        )
        return int(result.scalar_one())


class SqlIdempotencyRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def get(self, tenant_id: str, key: str) -> StoredResponse | None:
        row = (
            await self._conn.execute(
                text(
                    "SELECT job_id, status, body, created_at FROM idempotency_keys "
                    "WHERE tenant_id = :t AND key = :k "
                    "AND created_at > now() - interval '24 hours'"
                ),
                {"t": tenant_id, "k": key},
            )
        ).one_or_none()
        if row is None:
            return None
        body: dict[str, Any] = dict(row.body)
        created: datetime = row.created_at
        return StoredResponse(job_id=row.job_id, status=row.status, body=body, created_at=created)

    async def put(self, tenant_id: str, key: str, response: StoredResponse) -> None:
        await self._conn.execute(
            text(
                "INSERT INTO idempotency_keys (tenant_id, key, job_id, status, body) "
                "VALUES (:t, :k, :job, :status, CAST(:body AS jsonb)) "
                "ON CONFLICT (tenant_id, key) DO NOTHING"
            ),
            {
                "t": tenant_id,
                "k": key,
                "job": response.job_id,
                "status": response.status,
                "body": _json(response.body),
            },
        )


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
