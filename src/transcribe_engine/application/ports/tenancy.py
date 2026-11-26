"""Tenant limits and idempotency ports (S08, D-025)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

__all__ = ["IdempotencyRepository", "StoredResponse", "TenantLimits", "TenantRepository"]


@dataclass(frozen=True)
class TenantLimits:
    tenant_id: str
    max_active_jobs: int
    quota_audio_ms: int | None  # None = unlimited


@dataclass(frozen=True)
class StoredResponse:
    job_id: str
    status: int
    body: dict[str, Any]
    created_at: datetime
    request_hash: str  # binds the key to one request body (D-027)


class TenantRepository(Protocol):
    async def lock(self, tenant_id: str) -> None:
        """Serialize writes for this tenant until the unit of work ends (D-027)."""
        ...

    async def limits(self, tenant_id: str) -> TenantLimits | None: ...

    async def count_active_jobs(self, tenant_id: str) -> int: ...

    async def used_audio_ms(self, tenant_id: str) -> int: ...


class IdempotencyRepository(Protocol):
    async def get(self, tenant_id: str, key: str) -> StoredResponse | None:
        """A stored response younger than 24 hours, or None (D-025)."""
        ...

    async def put(self, tenant_id: str, key: str, response: StoredResponse) -> None: ...
