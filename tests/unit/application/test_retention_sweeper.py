"""S21 retention (AC-4): expired audio is removed according to the tenant's own retention setting.

Fake clock and fake storage, so no time passes and no network is used. Each refusal has a positive
control: the job inside its tenant's window keeps its audio, and the other tenant's job of the same
age is kept because its window is longer.
"""

import importlib
from datetime import timedelta
from types import ModuleType

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.storage import FakeObjectStorage


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


@pytest.mark.xfail(strict=True, reason="S21")
async def test_expired_audio_removed_per_tenant_setting() -> None:
    """AC-4: a 40-day-old job of a 30-day tenant loses its audio; the same age under a 90-day tenant
    keeps it; a 10-day-old job keeps it. The sweep reports exactly one audio deletion."""
    retention = _mod("transcribe_engine.application.use_cases.retention_sweeper")
    domain_storage = _mod("transcribe_engine.domain.storage_keys")
    clock = FakeClock()
    now = clock.now()
    store = _mod("tests.fakes.deletion").FakeDeletionStore(
        retention_days={"tenant-a": 30, "tenant-b": 90}
    )
    store.add_job("tenant-a", "job-a-old", created_at=now - timedelta(days=40))
    store.add_job("tenant-a", "job-a-new", created_at=now - timedelta(days=10))
    store.add_job("tenant-b", "job-b-old", created_at=now - timedelta(days=40))
    storage = FakeObjectStorage()
    for tenant, job in (
        ("tenant-a", "job-a-old"),
        ("tenant-a", "job-a-new"),
        ("tenant-b", "job-b-old"),
    ):
        await storage.put(domain_storage.work_key(tenant, job, "audio.wav"), b"RIFF")

    def make_uow(tenant_id: str | None = None) -> object:
        return store.uow()

    sweeper = retention.RetentionSweeper(make_uow, storage, clock)
    report = await sweeper.run_once(now)

    assert report.audio_deleted == 1
    assert await storage.head(domain_storage.work_key("tenant-a", "job-a-old", "audio.wav")) is None
    assert (
        await storage.head(domain_storage.work_key("tenant-a", "job-a-new", "audio.wav"))
        is not None
    )
    assert (
        await storage.head(domain_storage.work_key("tenant-b", "job-b-old", "audio.wav"))
        is not None
    )
    assert store.audio_deleted_for() == ["job-a-old"]
