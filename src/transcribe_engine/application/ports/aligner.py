"""Aligner port (S14, D-070): place known text on the audio of one chunk, returning word times.

The text comes from an ASR that reports no word timestamps. Word times are relative to the start
of the chunk's padded window, in integer samples (CLAUDE.md time units).
"""

from typing import Protocol

from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.merge import RawWord

__all__ = ["Aligner"]


class Aligner(Protocol):
    async def align(
        self, audio_key: str, chunk: Chunk, text: str, *, language: str
    ) -> tuple[RawWord, ...]: ...
