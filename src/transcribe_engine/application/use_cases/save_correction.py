"""Save a human correction as a new transcript version (S22, design: التصحيح البشري).

- Optimistic concurrency: `base_version` must be the latest version, otherwise
  StaleVersionError (409).
- Only the segments that changed are re-aligned (S14). Unchanged words keep their times (AC-1).
- The new version has source "human". Speaker renames apply to the whole version.
"""

from dataclasses import replace

from transcribe_engine.application.errors import (
    InvalidEditError,
    StaleVersionError,
    TranscriptNotFoundError,
)
from transcribe_engine.application.ports.versions import SegmentAligner, TranscriptVersions
from transcribe_engine.domain.corrections import Edit, apply_edits, merge_timings
from transcribe_engine.domain.transcript import CanonicalTranscript, Segment

__all__ = ["SaveCorrection"]


class SaveCorrection:
    def __init__(self, versions: TranscriptVersions, aligner: SegmentAligner) -> None:
        self._versions = versions
        self._aligner = aligner

    async def __call__(
        self,
        tenant_id: str,
        transcript_id: str,
        base_version: int,
        edits: tuple[Edit, ...],
        speaker_renames: dict[str, str],
    ) -> int:
        latest = await self._versions.latest(tenant_id, transcript_id)
        if latest is None:
            raise TranscriptNotFoundError
        if latest.version != base_version:
            raise StaleVersionError
        try:
            edited, changed = apply_edits(latest.segments, edits)
        except ValueError as exc:
            raise InvalidEditError from exc
        originals = {segment.id: segment for segment in latest.segments}
        final: list[Segment] = []
        for edited_segment in edited:
            if edited_segment.id not in changed:
                final.append(edited_segment)
                continue
            text = " ".join(word.text for word in edited_segment.words)
            aligned = await self._aligner.realign(
                transcript_id,
                edited_segment.id,
                edited_segment.start_ms,
                edited_segment.end_ms,
                text,
            )
            words = merge_timings(originals[edited_segment.id].words, edited_segment.words, aligned)
            final.append(replace(edited_segment, words=words))
        speakers = tuple(
            replace(speaker, label=speaker_renames.get(speaker.id, speaker.label))
            for speaker in latest.speakers
        )
        new_version: CanonicalTranscript = replace(
            latest,
            version=latest.version + 1,
            source="human",
            segments=tuple(final),
            speakers=speakers,
        )
        await self._versions.save(tenant_id, new_version)
        return new_version.version
