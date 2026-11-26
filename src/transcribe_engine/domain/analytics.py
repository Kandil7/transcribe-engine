"""Speaker analytics (S19, design: الإثراء). Pure domain logic, no model.

- talk time: the sum of a speaker's segment durations (the segment is the unit of speech).
- words per minute: the speaker's word count over their talk time.
- turns: runs of consecutive segments by the same speaker; a change of speaker starts a new turn.
- silence: the time between the first start and the last end with no segment speaking.
"""

from dataclasses import dataclass

from transcribe_engine.domain.transcript import CanonicalTranscript

__all__ = ["SpeakerAnalytics", "SpeakerStats", "speaker_analytics"]

_MS_PER_MINUTE = 60_000


@dataclass(frozen=True)
class SpeakerStats:
    speaker: str
    talk_ms: int
    words: int
    words_per_minute: float
    turns: int


@dataclass(frozen=True)
class SpeakerAnalytics:
    speakers: tuple[SpeakerStats, ...]
    silence_ms: int


def speaker_analytics(transcript: CanonicalTranscript) -> SpeakerAnalytics:
    talk: dict[str, int] = {}
    words: dict[str, int] = {}
    turns: dict[str, int] = {}
    previous: str | None = None
    for segment in transcript.segments:
        speaker = segment.speaker
        if speaker is None:
            previous = None
            continue
        talk[speaker] = talk.get(speaker, 0) + (segment.end_ms - segment.start_ms)
        words[speaker] = words.get(speaker, 0) + len(segment.words)
        if speaker != previous:
            turns[speaker] = turns.get(speaker, 0) + 1
        previous = speaker
    stats = tuple(
        SpeakerStats(
            speaker=speaker,
            talk_ms=talk[speaker],
            words=words.get(speaker, 0),
            words_per_minute=_rate(words.get(speaker, 0), talk[speaker]),
            turns=turns.get(speaker, 0),
        )
        for speaker in talk
    )
    return SpeakerAnalytics(speakers=stats, silence_ms=_silence_ms(transcript))


def _rate(words: int, talk_ms: int) -> float:
    if talk_ms <= 0:
        return 0.0
    return words * _MS_PER_MINUTE / talk_ms


def _silence_ms(transcript: CanonicalTranscript) -> int:
    spans = sorted((s.start_ms, s.end_ms) for s in transcript.segments if s.end_ms > s.start_ms)
    if not spans:
        return 0
    total = spans[-1][1] - spans[0][0]
    speech = 0
    current_start, current_end = spans[0]
    for start, end in spans[1:]:
        if start > current_end:
            speech += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    speech += current_end - current_start
    return total - speech
