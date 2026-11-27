"""S21 runner isolation (D-060): one job whose deletion is refused does not stop the others. Each
refusal has a positive control: the other job is removed, and the refused job stays pending.
"""

import importlib
from datetime import UTC, datetime
from types import ModuleType

from tests.fakes.clock import FakeClock
from tests.fakes.deletion import FakeDeletionStore
from tests.fakes.storage import FakeObjectStorage


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def test_refused_job_does_not_stop_the_others() -> None:
    """The first marked job is refused; the second is still deleted.

    The run reports both as handled."""
    deletion = _mod("transcribe_engine.application.use_cases.delete_job_data")
    store = FakeDeletionStore()
    store.requested = [("tenant-a", "job-refused"), ("tenant-a", "job-ok")]
    store.fail_on = {"job-refused"}

    def make_uow(tenant_id: str | None = None) -> object:
        return store.uow()

    handled = await deletion.run_requested_deletions(
        make_uow, FakeObjectStorage(), FakeClock(current=datetime(2026, 11, 27, tzinfo=UTC))
    )
    assert handled == 2
    assert store.removed == ["job-ok"]  # positive control: the good job was deleted
    assert "job-refused" not in store.removed  # the refused job stays pending for the next run
