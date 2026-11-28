"""Segment realigner (S22, R-005, D-070): word times for a corrected segment.

A correction that changes a segment's text needs new word times. This adapter cuts the segment's
span from the job's normalized file, places the text on the frames with the forced aligner, and
returns the words in absolute milliseconds inside the segment. A model failure or missing audio is
an AlignmentUnavailableError (503): the correction is refused, never saved with invented times.
"""

from collections.abc import Sequence

from transcribe_engine.application.errors import AlignmentUnavailableError
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.chunks import NORMALIZED_SAMPLE_RATE
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.storage_keys import work_key
from transcribe_engine.domain.transcript import Word
from transcribe_engine.infrastructure.alignment.wav2vec2_aligner import Wav2Vec2Aligner

__all__ = ["NORMALIZED_NAME", "SegmentRealigner"]

# The normalized file's name in a job's working prefix (ingest_job.WAV_NAME).
NORMALIZED_NAME = "audio.wav"


class SegmentRealigner:
    def __init__(self, storage: ObjectStorage, aligner: Wav2Vec2Aligner, *, language: str) -> None:
        self._storage = storage
        self._aligner = aligner
        self._language = language

    async def realign(
        self,
        tenant_id: str,
        transcript_id: str,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        text: str,
    ) -> Sequence[Word]:
        del segment_id
        if not text.strip():
            return ()
        rate = NORMALIZED_SAMPLE_RATE
        start_sample = start_ms * rate // 1000
        end_sample = end_ms * rate // 1000
        audio_key = work_key(tenant_id, transcript_id, NORMALIZED_NAME)
        try:
            raw = await self._aligner.align_span(audio_key, start_sample, end_sample, text)
        except PermanentError as exc:
            raise AlignmentUnavailableError from exc
        words: list[Word] = []
        for item in raw:
            begin = (start_sample + item.local_start) * 1000 // rate
            finish = (start_sample + item.local_end) * 1000 // rate
            words.append(
                Word(
                    text=item.text,
                    start_ms=min(max(begin, start_ms), end_ms),
                    end_ms=min(max(finish, start_ms), end_ms),
                    lang=self._language,
                    conf=item.conf,
                )
            )
        return tuple(words)
