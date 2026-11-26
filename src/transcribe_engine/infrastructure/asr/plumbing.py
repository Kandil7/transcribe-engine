"""Plumbing ASR (S10, D-035): returns no words. It lets the pipeline run end to end before a model
exists (S12). Its transcripts are empty by design and must never be read as recognition output."""

from transcribe_engine.application.ports.asr import ASRCapabilities
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.merge import RawWord

__all__ = ["PlumbingASR"]


class PlumbingASR:
    name = "plumbing"
    revision = "none"
    capabilities = ASRCapabilities(
        native_word_timestamps=False,
        native_segment_timestamps=False,
        max_chunk_seconds=0.0,
        supports_language_hint=False,
        supports_batching=False,
    )

    async def transcribe(
        self, audio_key: str, chunk: Chunk, *, language: str
    ) -> tuple[RawWord, ...]:
        return ()
