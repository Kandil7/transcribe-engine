"""S17 (R-008, D-072): the Sortformer adapter turns its segments into speaker turns in milliseconds.

NeMo is not installed here, so the model is a fake that returns the segment lines Sortformer prints:
"begin_seconds end_seconds speaker_index". Positive controls: two speakers keep their order and ids;
a malformed line is refused rather than guessed; the adapter hands the model a real local file.
"""

import importlib
import os
from types import ModuleType
from typing import Any

import pytest

from tests.fakes.storage import FakeObjectStorage
from transcribe_engine.domain.errors import PermanentError


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


class _Model:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.seen_paths: list[str] = []

    def diarize(self, path: str) -> list[str]:
        assert os.path.exists(path), "the adapter must hand the model a local file"
        self.seen_paths.append(path)
        return self._lines


async def _run(lines: list[str]) -> Any:
    sortformer = _mod("transcribe_engine.infrastructure.diarization.sortformer")
    storage = FakeObjectStorage()
    await storage.put("work/t/j/audio.wav", b"RIFF" + b"\x00" * 64)
    adapter = sortformer.SortformerDiarizer(storage, _Model(lines))
    return await adapter.diarize("work/t/j/audio.wav", None)


async def test_segments_become_speaker_turns_in_ms() -> None:
    turns = await _run(["0.00 1.50 0", "1.50 3.25 1"])
    assert [(t.speaker, t.start_ms, t.end_ms) for t in turns] == [
        ("spk0", 0, 1_500),
        ("spk1", 1_500, 3_250),
    ]


async def test_malformed_segment_is_refused() -> None:
    with pytest.raises(PermanentError):
        await _run(["0.00 one 0"])
