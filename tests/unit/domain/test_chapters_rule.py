"""S19 chapters by rule (D-081): a chapter closes at a long pause once it is long enough.

Each check has a positive control (a pause that is long enough does start a chapter), so a rule that
never splits cannot pass.
"""

import importlib
from types import ModuleType

from transcribe_engine.domain.transcript import Segment, Word


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _segment(index: int, start_ms: int, end_ms: int, words: int = 4) -> Segment:
    step = max(1, (end_ms - start_ms) // max(1, words))
    return Segment(
        id=f"seg-{index}",
        start_ms=start_ms,
        end_ms=end_ms,
        speaker=None,
        words=tuple(
            Word(f"s{index}w{i}", start_ms + i * step, start_ms + i * step + step - 1, "ar", None)
            for i in range(words)
        ),
    )


def test_a_long_pause_after_a_long_enough_chapter_starts_a_new_chapter() -> None:
    """Two 40-second segments with a 3-second pause between them: two chapters, the second starting
    at the second segment. Positive control: without the pause there is one chapter."""
    rule = _mod("transcribe_engine.domain.chapters").rule_chapters
    first = _segment(0, 0, 40_000)
    second = _segment(1, 43_000, 83_000)
    chapters = rule((first, second))
    assert [c.start_ms for c in chapters] == [0, 43_000]
    assert chapters[1].end_ms == 83_000
    joined = rule((first, _segment(1, 40_000, 80_000)))
    assert len(joined) == 1


def test_a_short_pause_does_not_start_a_chapter() -> None:
    """A pause of 1 second is below the 2-second minimum, so the segments stay one chapter."""
    rule = _mod("transcribe_engine.domain.chapters").rule_chapters
    chapters = rule((_segment(0, 0, 40_000), _segment(1, 41_000, 81_000)))
    assert len(chapters) == 1


def test_a_short_chapter_does_not_close_at_a_long_pause() -> None:
    """A chapter of 10 seconds is below the 30-second minimum, so a long pause after it does not
    start a new chapter (no chapter is cut into pieces too short to be useful)."""
    rule = _mod("transcribe_engine.domain.chapters").rule_chapters
    chapters = rule((_segment(0, 0, 10_000), _segment(1, 20_000, 60_000)))
    assert len(chapters) == 1


def test_the_first_chapter_starts_at_zero_even_when_speech_starts_later() -> None:
    """Speech that starts at 5 seconds still gives a first chapter at 0, as YouTube requires."""
    rule = _mod("transcribe_engine.domain.chapters").rule_chapters
    chapters = rule((_segment(0, 5_000, 45_000),))
    assert chapters[0].start_ms == 0
    assert chapters[0].end_ms == 45_000


def test_titles_are_the_first_six_words_of_the_chapter() -> None:
    """The title is six words from the transcript itself, never invented."""
    rule = _mod("transcribe_engine.domain.chapters").rule_chapters
    chapters = rule((_segment(0, 0, 40_000, words=10),))
    assert chapters[0].title == "s0w0 s0w1 s0w2 s0w3 s0w4 s0w5"


def test_empty_transcript_has_no_chapters() -> None:
    rule = _mod("transcribe_engine.domain.chapters").rule_chapters
    assert rule(()) == ()
