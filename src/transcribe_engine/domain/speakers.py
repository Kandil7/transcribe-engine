"""Speaker turns and word assignment (S17, design: 6. Speaker Diarization). Pure domain logic.

A word takes the speaker whose turn overlaps it the most. A word whose time overlaps the speech of
two different speakers is flagged `overlap` (the design: overlapping speech). A word that no turn
overlaps has no speaker. Times are integer milliseconds at this boundary (CLAUDE.md).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from transcribe_engine.domain.merge import Word

__all__ = ["SpeakerTurn", "assign_speakers"]


@dataclass(frozen=True)
class SpeakerTurn:
    speaker: str
    start_ms: int
    end_ms: int


def assign_speakers(words: Sequence[Word], turns: Sequence[SpeakerTurn]) -> tuple[Word, ...]:
    """Return the words with `speaker` and `overlap` set. Input order is kept."""
    return tuple(_assign(word, turns) for word in words)


def _assign(word: Word, turns: Sequence[SpeakerTurn]) -> Word:
    overlaps: dict[str, int] = {}
    for turn in turns:
        amount = min(word.end_ms, turn.end_ms) - max(word.start_ms, turn.start_ms)
        if amount > 0:
            overlaps[turn.speaker] = overlaps.get(turn.speaker, 0) + amount
    if not overlaps:
        return replace(word, speaker=None, overlap=False)
    # The largest overlap wins. A tie goes to the speaker whose name sorts first (stable).
    best = min(overlaps, key=lambda speaker: (-overlaps[speaker], speaker))
    return replace(word, speaker=best, overlap=len(overlaps) > 1)
