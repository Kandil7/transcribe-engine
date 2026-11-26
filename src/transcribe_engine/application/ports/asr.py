"""ASR port (S10): transcribe one chunk of the normalized audio.

The adapter reads the chunk's padded window from storage (S3 Range GET, no per-chunk files) and
returns words in local sample offsets from the start of that window. Permanent failures raise
PermanentError; the chunk policy decides what they mean for the job (process_job.py). Transient
failures raise TransientError and the worker retries the job.
"""

from typing import Protocol

from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.merge import RawWord

__all__ = ["ASREngine"]


class ASREngine(Protocol):
    async def transcribe(
        self, audio_key: str, chunk: Chunk, *, language: str
    ) -> tuple[RawWord, ...]: ...
