"""Run the aligner, and fall back to segment times only when alignment fails for good (S14, D-077).

A permanent aligner failure gives segment times flagged as fallback. A transient failure is not a
fallback: it propagates, so the job is retried and the words are aligned on the retry.
"""

from transcribe_engine.application.ports.aligner import Aligner
from transcribe_engine.domain.alignment_fallback import segment_times
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.merge import RawWord

__all__ = ["align_or_fallback"]


async def align_or_fallback(
    aligner: Aligner,
    audio_key: str,
    chunk: Chunk,
    text: str,
    *,
    language: str,
) -> tuple[RawWord, ...]:
    try:
        return await aligner.align(audio_key, chunk, text, language=language)
    except PermanentError:
        window_start = max(0, chunk.start_sample - chunk.pad_before)
        window_end = chunk.end_sample + chunk.pad_after
        core_start = chunk.start_sample - window_start
        core_end = core_start + (chunk.end_sample - chunk.start_sample)
        return segment_times(text, core_start, min(core_end, window_end - window_start))
