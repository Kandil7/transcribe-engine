"""Diff between two versions of one transcript (S22, design: التصحيح البشري). Pure domain logic.

Words are compared per segment with a sequence matcher, so a replaced, inserted or deleted word is
reported once with its before and after text. A speaker whose label changed is reported once. The
diffs feed the evaluation set and the terms dictionary (design).
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from transcribe_engine.domain.transcript import CanonicalTranscript

__all__ = ["TranscriptDiff", "WordChange", "diff_versions"]

_KINDS: dict[str, Literal["replace", "insert", "delete"]] = {
    "replace": "replace",
    "insert": "insert",
    "delete": "delete",
}


@dataclass(frozen=True)
class WordChange:
    segment_id: str
    kind: Literal["replace", "insert", "delete"]
    before: tuple[str, ...]
    after: tuple[str, ...]


@dataclass(frozen=True)
class TranscriptDiff:
    word_changes: tuple[WordChange, ...]
    speaker_renames: tuple[tuple[str, str, str], ...]  # (speaker id, old label, new label)


def diff_versions(a: CanonicalTranscript, b: CanonicalTranscript) -> TranscriptDiff:
    """What changed from version `a` to version `b`."""
    b_segments = {segment.id: segment for segment in b.segments}
    changes: list[WordChange] = []
    for segment in a.segments:
        other = b_segments.get(segment.id)
        if other is None:
            continue
        before = [word.text for word in segment.words]
        after = [word.text for word in other.words]
        matcher = SequenceMatcher(None, before, after, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            kind = _KINDS.get(tag)
            if kind is None:  # "equal": nothing changed
                continue
            changes.append(WordChange(segment.id, kind, tuple(before[i1:i2]), tuple(after[j1:j2])))
    old_labels = {speaker.id: speaker.label for speaker in a.speakers}
    renames = tuple(
        (speaker.id, old_labels[speaker.id], speaker.label)
        for speaker in b.speakers
        if speaker.id in old_labels and old_labels[speaker.id] != speaker.label
    )
    return TranscriptDiff(word_changes=tuple(changes), speaker_renames=renames)
