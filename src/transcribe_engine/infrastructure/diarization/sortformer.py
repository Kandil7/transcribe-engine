"""Diarizer port over NVIDIA Sortformer (S17, D-072).

Model: nvidia/diar_streaming_sortformer_4spk-v2 (CC-BY-4.0), pinned below.

- The model is a NeMo object with diarize(path). It prints one segment per line:
  "begin end speaker", in seconds, and the speaker index. NeMo is not a dependency of this repo
  yet; the model is passed in (the loader waits for the owner's dependency approval, D-072).
- The model reads a file, so the adapter writes the stored audio to a temporary file and
  removes it.
- Times leave the model in seconds and become integer milliseconds here, once (CLAUDE.md units).
- A segment that cannot be read, or ends before it starts, is a PermanentError; nothing is guessed.
"""

import asyncio
import os
import tempfile
from collections.abc import Sequence
from typing import Protocol

from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.speakers import SpeakerTurn

__all__ = ["SortformerDiarizer"]

SORTFORMER_REVISION = (
    "84edd514b8ef68004c10086918cd62f2148cbd59"  # nvidia/diar_streaming_sortformer_4spk-v2
)
_MAX_SPEAKERS = 4  # the checkpoint's published limit


class SegmentModel(Protocol):
    def diarize(self, path: str) -> Sequence[str]: ...


class SortformerDiarizer:
    name = "nvidia-sortformer"
    revision = SORTFORMER_REVISION
    max_speakers: int | None = _MAX_SPEAKERS

    def __init__(self, storage: ObjectStorage, model: SegmentModel) -> None:
        self._storage = storage
        self._model = model

    async def diarize(self, audio_key: str, num_speakers: int | None) -> Sequence[SpeakerTurn]:
        info = await self._storage.head(audio_key)
        if info is None:
            raise PermanentError("audio for diarization is missing")
        data = await self._storage.read_range(audio_key, 0, info.size)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(data)
            path = handle.name
        try:
            lines = await asyncio.to_thread(self._run, path)
        finally:
            os.remove(path)
        return _turns(lines)

    def _run(self, path: str) -> Sequence[str]:
        try:
            return self._model.diarize(path)
        except Exception as exc:  # the model failed on this file: permanent for the job's speakers
            raise PermanentError("diarization model failed") from exc


def _turns(lines: Sequence[str]) -> tuple[SpeakerTurn, ...]:
    turns: list[SpeakerTurn] = []
    for line in lines:
        fields = line.split()
        if len(fields) != 3:
            raise PermanentError("diarization segment is malformed")
        try:
            begin, end, speaker = float(fields[0]), float(fields[1]), int(fields[2])
        except ValueError as exc:
            raise PermanentError("diarization segment is malformed") from exc
        if speaker < 0 or end < begin or begin < 0:
            raise PermanentError("diarization segment is out of range")
        turns.append(
            SpeakerTurn(
                speaker=f"spk{speaker}",
                start_ms=round(begin * 1000),
                end_ms=round(end * 1000),
            )
        )
    return tuple(turns)
