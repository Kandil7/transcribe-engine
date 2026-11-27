"""Human corrections on a transcript version (S22, design: التصحيح البشري). Pure domain logic.

An edit replaces words `word_index_from` (inclusive) to `word_index_to` (exclusive) of one segment
with the words of `new_text`. New words have no time yet. The caller re-aligns only the changed
segments and merges the result with `merge_timings`: a word that did not change keeps its old time,
and only new or changed words take the aligner's time (AC-1).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from transcribe_engine.domain.transcript import Segment, Word

__all__ = ["Edit", "apply_edits", "merge_timings"]


@dataclass(frozen=True)
class Edit:
    segment_id: str
    word_index_from: int
    word_index_to: int
    new_text: str


def apply_edits(
    segments: Sequence[Segment], edits: Sequence[Edit]
) -> tuple[tuple[Segment, ...], frozenset[str]]:
    """The segments after the edits, and the ids of the segments that changed.

    Edits to one segment are applied from the last word to the first, so earlier indexes stay valid.
    """
    by_segment: dict[str, list[Edit]] = {}
    for edit in edits:
        by_segment.setdefault(edit.segment_id, []).append(edit)
    known = {segment.id for segment in segments}
    unknown = set(by_segment) - known
    if unknown:
        raise ValueError(f"edit names a segment that is not in the transcript: {sorted(unknown)}")
    out: list[Segment] = []
    changed: set[str] = set()
    for segment in segments:
        segment_edits = by_segment.get(segment.id)
        if not segment_edits:
            out.append(segment)
            continue
        words = list(segment.words)
        for edit in sorted(segment_edits, key=lambda e: e.word_index_from, reverse=True):
            if not 0 <= edit.word_index_from <= edit.word_index_to <= len(words):
                raise ValueError("edit word indexes are outside the segment")
            new_words = [
                Word(text=text, start_ms=0, end_ms=0, lang=_lang(segment), conf=None)
                for text in edit.new_text.split()
            ]
            words[edit.word_index_from : edit.word_index_to] = new_words
        out.append(replace(segment, words=tuple(words)))
        changed.add(segment.id)
    return tuple(out), frozenset(changed)


def merge_timings(
    old: Sequence[Word], new: Sequence[Word], aligned: Sequence[Word]
) -> tuple[Word, ...]:
    """The corrected words with times. Words equal to an old word keep its time and confidence; the
    rest take the aligner's word at the same position."""
    matcher = SequenceMatcher(None, [w.text for w in old], [w.text for w in new], autojunk=False)
    kept: dict[int, Word] = {}
    for tag, i1, i2, j1, _ in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                kept[j1 + offset] = old[i1 + offset]
    out: list[Word] = []
    for index, word in enumerate(new):
        if index in kept:
            out.append(
                replace(
                    word,
                    start_ms=kept[index].start_ms,
                    end_ms=kept[index].end_ms,
                    conf=kept[index].conf,
                )
            )
        elif aligned:
            source = aligned[min(index, len(aligned) - 1)]
            out.append(replace(word, start_ms=source.start_ms, end_ms=source.end_ms))
        else:
            out.append(word)
    return tuple(out)


def _lang(segment: Segment) -> str:
    return segment.words[0].lang if segment.words else "ar"
