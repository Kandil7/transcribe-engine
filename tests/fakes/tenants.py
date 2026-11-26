"""In-memory tenant limits, idempotency, and a unit of work that exposes them (S08 fakes).

Limits and idempotency records live on the shared FakeTenants object.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Self

from tests.fakes.repositories import FakeStore, FakeUnitOfWork
from transcribe_engine.application.ports.tenancy import StoredResponse, TenantLimits
from transcribe_engine.domain.jobs import JobState

__all__ = ["FakeApiUnitOfWork", "FakeTenants"]

ACTIVE = {
    JobState.QUEUED,
    JobState.PENDING_VALIDATION,
    JobState.PROCESSING,
    JobState.RETRY_SCHEDULED,
}


@dataclass
class FakeTenants:
    limits_by_tenant: dict[str, TenantLimits] = field(default_factory=dict)
    idempotency: dict[tuple[str, str], StoredResponse] = field(default_factory=dict)
    _store: FakeStore | None = None

    def bind(self, store: FakeStore) -> None:
        self._store = store

    def add(
        self, tenant_id: str, *, max_active_jobs: int = 5, quota_audio_ms: int | None = None
    ) -> None:
        self.limits_by_tenant[tenant_id] = TenantLimits(tenant_id, max_active_jobs, quota_audio_ms)

    def set_limit(self, tenant_id: str, *, max_active_jobs: int) -> None:
        current = self.limits_by_tenant.get(tenant_id)
        quota = current.quota_audio_ms if current else None
        self.limits_by_tenant[tenant_id] = TenantLimits(tenant_id, max_active_jobs, quota)

    async def lock(self, tenant_id: str) -> None:
        return None  # the fake runs one request at a time; the SQL version takes a row lock

    async def limits(self, tenant_id: str) -> TenantLimits | None:
        return self.limits_by_tenant.get(tenant_id)

    async def count_active_jobs(self, tenant_id: str) -> int:
        assert self._store is not None
        return sum(
            1
            for job in self._store.jobs.values()
            if job.tenant_id == tenant_id and job.state in ACTIVE
        )

    async def used_audio_ms(self, tenant_id: str) -> int:
        assert self._store is not None
        return sum(
            m.duration_ms
            for m in self._store.media_by_tenant_sha.values()
            if m.tenant_id == tenant_id
        )


class _IdempotencyView:
    def __init__(self, tenants: FakeTenants) -> None:
        self._tenants = tenants

    async def get(self, tenant_id: str, key: str) -> StoredResponse | None:
        stored = self._tenants.idempotency.get((tenant_id, key))
        if stored is None or datetime.now(UTC) - stored.created_at > timedelta(hours=24):
            return None
        return stored

    async def put(self, tenant_id: str, key: str, response: StoredResponse) -> None:
        existing = self._tenants.idempotency.get((tenant_id, key))
        if existing is None or datetime.now(UTC) - existing.created_at > timedelta(hours=24):
            self._tenants.idempotency[(tenant_id, key)] = response


class FakeApiUnitOfWork(FakeUnitOfWork):
    def __init__(self, store: FakeStore, tenants: FakeTenants) -> None:
        super().__init__(store)
        tenants.bind(store)
        self.tenants = tenants
        self.idempotency = _IdempotencyView(tenants)

    async def __aenter__(self) -> Self:
        return self
