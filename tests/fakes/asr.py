"""In-memory ASR for unit and integration tests (S10). Scripted output, counted calls.

`script` maps a chunk id to the words the fake returns for it. `fail_permanent` lists chunk ids
whose transcription raises PermanentError. `calls` counts invocations per chunk id, which is what
the resume test asserts (AC-7).
"""

from collections import Counter
from dataclasses import dataclass, field

from transcribe_engine.application.ports.asr import ASRCapabilities
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.merge import RawWord


@dataclass
class FakeASR:
    script: dict[str, tuple[RawWord, ...]] = field(default_factory=dict)
    fail_permanent: set[str] = field(default_factory=set)
    calls: Counter[str] = field(default_factory=Counter)
    name: str = "fake"
    revision: str = "fake-1"
    capabilities: ASRCapabilities = field(
        default_factory=lambda: ASRCapabilities(
            native_word_timestamps=True,
            native_segment_timestamps=False,
            max_chunk_seconds=3600.0,
            supports_language_hint=True,
            supports_batching=True,
        )
    )

    async def transcribe(
        self, audio_key: str, chunk: Chunk, *, language: str
    ) -> tuple[RawWord, ...]:
        self.calls[chunk.chunk_id] += 1
        if chunk.chunk_id in self.fail_permanent:
            raise PermanentError("fake ASR refused this chunk")
        return self.script.get(chunk.chunk_id, ())
