"""ASR port (S10, extended in S12): transcribe one chunk of the normalized audio.

The adapter reads the chunk's padded window from storage (S3 Range GET, no per-chunk files) and
returns words in local sample offsets from the start of that window. Permanent failures raise
PermanentError; the chunk policy decides what they mean for the job (process_job.py). Transient
failures raise TransientError and the worker retries the job.

Every engine declares its name, revision (recorded as provenance) and capabilities (S12). The
decoding options are fixed inside each adapter for now (D-041).
"""

from dataclasses import dataclass
from typing import Protocol

from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.merge import RawWord

__all__ = ["ASRCapabilities", "ASREngine"]


@dataclass(frozen=True)
class ASRCapabilities:
    native_word_timestamps: bool
    native_segment_timestamps: bool
    max_chunk_seconds: float
    supports_language_hint: bool
    supports_batching: bool


class ASREngine(Protocol):
    name: str
    revision: str
    capabilities: ASRCapabilities

    async def transcribe(
        self, audio_key: str, chunk: Chunk, *, language: str
    ) -> tuple[RawWord, ...]: ...
