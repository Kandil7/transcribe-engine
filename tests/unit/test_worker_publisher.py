"""S20 shutdown: the publisher worker closes its webhook HTTP client when it stops (review finding).

Positive control: the publisher ran at least once before it stopped, so the close is not just a
test of an idle loop. A stop that is an error still propagates, so a failure is never hidden.
"""

import importlib
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


class _Sender:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _Publisher:
    def __init__(self, stop_after: int) -> None:
        self.calls = 0
        self._stop_after = stop_after

    async def run_once(self) -> int:
        self.calls += 1
        if self.calls > self._stop_after:
            raise RuntimeError("publisher stopped")
        return 1  # a delivered row, so the loop does not sleep


async def test_publisher_closes_its_sender_when_it_stops() -> None:
    worker = _mod("transcribe_engine.worker")
    sender: Any = _Sender()
    publisher: Any = _Publisher(stop_after=2)
    settings = SimpleNamespace(poll_seconds=0)
    with pytest.raises(RuntimeError, match="publisher stopped"):
        await worker.run_publisher(publisher, sender, settings)
    assert publisher.calls == 3  # the loop ran (positive control), then stopped
    assert sender.closed is True
