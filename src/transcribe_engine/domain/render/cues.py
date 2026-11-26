"""Cue builder (S15, design: الترجمات المرئية). A cue is a subtitle, not a segment: a segment can
hold several cues, and a cue never crosses a speaker change when `break_on_speaker_change` is set.

Rules, in order of precedence:
- A cue fits its profile: at most `max_lines` lines of `max_chars_per_line`, at most
  `max_duration_ms` long, and at most `max_cps` characters per second over its word span. A
  single word is never split, so it is exempt from the cps limit.
- A forced break is placed after a word that is not a preposition, so a preposition never ends a
  cue and stays with the word after it. Among the allowed places, a break before a conjunction
  is preferred, then the latest allowed place, so cues fill up.
- Sentence punctuation always ends a cue.
- Timing: a cue starts at its first word and ends at its last word. A short cue is extended to
  `min_duration_ms`, but its end is clamped to the next cue's start minus `min_gap_ms` and never
  falls below its last word (D-045).

Pure domain logic. Times are integer milliseconds.
"""

from dataclasses import dataclass
from typing import Literal

from transcribe_engine.domain.text import normalize
from transcribe_engine.domain.transcript import CanonicalTranscript, Word

__all__ = ["Cue", "SubtitleProfile", "build_cues"]

SENTENCE_PUNCTUATION = ".،,؟?!:;"
PREPOSITIONS = frozenset(normalize(p).search for p in ("في", "على", "من", "عن", "إلى", "مع"))
CONJUNCTIONS = frozenset(normalize(c).search for c in ("و", "ف", "ثم", "لكن", "أو", "بس"))
_ARABIC_INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


@dataclass(frozen=True)
class SubtitleProfile:
    max_chars_per_line: int = 42
    max_lines: int = 2
    min_duration_ms: int = 833
    max_duration_ms: int = 7000
    max_cps: float = 17.0  # Q1 of S15: initial value, to confirm with a viewer test
    min_gap_ms: int = 80
    break_on_speaker_change: bool = True
    numerals: Literal["western", "arabic_indic"] = "western"


@dataclass(frozen=True)
class Cue:
    start_ms: int
    end_ms: int
    lines: tuple[str, ...]
    speaker: str | None
    speaker_label: str | None
    word_count: int


def build_cues(transcript: CanonicalTranscript, profile: SubtitleProfile) -> tuple[Cue, ...]:
    labels = {s.id: s.label for s in transcript.speakers}
    drafts: list[tuple[list[Word], str | None]] = []
    pending: list[Word] = []
    pending_speaker: str | None = None
    for segment in transcript.segments:
        if pending and profile.break_on_speaker_change and segment.speaker != pending_speaker:
            drafts.append((pending, pending_speaker))
            pending = []
        if not pending:
            pending_speaker = segment.speaker
        for word in segment.words:
            while pending and not _fits([*pending, word], profile):
                head, pending = _split(pending, word)
                drafts.append((head, pending_speaker))
            pending.append(word)
            if _ends_sentence(word.text):
                drafts.append((pending, pending_speaker))
                pending = []
    if pending:
        drafts.append((pending, pending_speaker))
    return _finish(drafts, labels, profile)


def _ends_sentence(text: str) -> bool:
    return bool(text) and text[-1] in SENTENCE_PUNCTUATION


def _wrap(words: list[Word], profile: SubtitleProfile) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word.text])
        if current and len(candidate) > profile.max_chars_per_line:
            lines.append(" ".join(current))
            current = [word.text]
        else:
            current.append(word.text)
    if current:
        lines.append(" ".join(current))
    return lines


def _fits(words: list[Word], profile: SubtitleProfile) -> bool:
    if len(words) == 1:
        return True  # one word is never split
    if len(_wrap(words, profile)) > profile.max_lines:
        return False
    span = words[-1].end_ms - words[0].start_ms
    if span > profile.max_duration_ms:
        return False
    chars = len(" ".join(word.text for word in words))
    return chars * 1000 <= profile.max_cps * max(span, 1)


def _split(pending: list[Word], word: Word) -> tuple[list[Word], list[Word]]:
    """Split `pending` into the head to emit and the tail that stays pending.

    The head is never empty and the cut never follows a preposition. A cut before a conjunction is
    preferred; otherwise the latest allowed cut is taken. Pending fitted before `word` was added,
    so the head fits too.
    """
    allowed = [
        k for k in range(1, len(pending) + 1) if _norm(pending[k - 1].text) not in PREPOSITIONS
    ]
    if not allowed:
        allowed = [len(pending)]

    def next_text(k: int) -> str:
        return pending[k].text if k < len(pending) else word.text

    before_conjunction = [k for k in allowed if _norm(next_text(k)) in CONJUNCTIONS]
    cut = max(before_conjunction) if before_conjunction else max(allowed)
    return pending[:cut], pending[cut:]


def _norm(text: str) -> str:
    return normalize(text.rstrip(SENTENCE_PUNCTUATION)).search


def _finish(
    drafts: list[tuple[list[Word], str | None]],
    labels: dict[str, str],
    profile: SubtitleProfile,
) -> tuple[Cue, ...]:
    cues: list[Cue] = []
    for index, (words, speaker) in enumerate(drafts):
        start = words[0].start_ms
        last_end = words[-1].end_ms
        end = max(last_end, start + profile.min_duration_ms)
        if index + 1 < len(drafts):
            next_start = drafts[index + 1][0][0].start_ms
            end = max(last_end, min(end, next_start - profile.min_gap_ms))
        lines = tuple(_numerals(line, profile.numerals) for line in _wrap(words, profile))
        cues.append(
            Cue(
                start_ms=start,
                end_ms=end,
                lines=lines,
                speaker=speaker,
                speaker_label=labels.get(speaker) if speaker is not None else None,
                word_count=len(words),
            )
        )
    return tuple(cues)


def _numerals(text: str, mode: str) -> str:
    return text.translate(_ARABIC_INDIC) if mode == "arabic_indic" else text
