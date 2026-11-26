"""S15 cue builder (AC-3 profile limits as a property, AC-4 no preposition split).
Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
import itertools
from types import ModuleType
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ARABIC = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
_LABELS = {"S1": "SPEAKER_01", "S2": "SPEAKER_02"}
PREPOSITIONS = ("في", "على", "من", "عن", "إلى", "مع")

pytestmark = pytest.mark.xfail(strict=True, reason="S15")


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _transcript(words: list[tuple[str, int, int]], speaker: str = "S1") -> Any:
    t = _mod("transcribe_engine.domain.transcript")
    segment = t.Segment(
        id="seg-1",
        start_ms=words[0][1],
        end_ms=words[-1][2],
        speaker=speaker,
        words=tuple(
            t.Word(text=w, start_ms=s, end_ms=e, lang="ar", conf=None) for w, s, e in words
        ),
    )
    return t.CanonicalTranscript(
        schema_version="1.0",
        transcript_id="tr-1",
        version=1,
        source="asr",
        media=t.MediaMeta(media_id="media-1", duration_ms=words[-1][2], language="ar"),
        provenance=t.Provenance(
            engine="e", revision="r", pipeline_version="1", config_hash="c" * 64
        ),
        speakers=(t.Speaker(id=speaker, label=_LABELS[speaker]),),
        segments=(segment,),
        events=(),
        warnings=(),
    )


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.text(alphabet=ARABIC, min_size=1, max_size=10),
            st.integers(min_value=100, max_value=900),  # word duration, ms
            st.integers(min_value=80, max_value=1500),  # gap before the next word, ms
        ),
        min_size=1,
        max_size=60,
    )
)
def test_profile_limits_hold(spec: list[tuple[str, int, int]]) -> None:
    """AC-3: lines, chars per line, cue duration, reading speed and gaps stay in the profile
    limits. Words are at most 10 characters, so one word cannot overflow a line by itself.
    Reading speed is exempt for a single-word cue, which cannot be split further."""
    cues_mod = _mod("transcribe_engine.domain.render.cues")
    profile = cues_mod.SubtitleProfile()
    words: list[tuple[str, int, int]] = []
    cursor = 0
    for text, duration, gap in spec:
        words.append((text, cursor, cursor + duration))
        cursor += duration + gap
    cues = cues_mod.build_cues(_transcript(words), profile)
    assert cues
    for cue in cues:
        assert len(cue.lines) <= profile.max_lines
        for line in cue.lines:
            assert len(line) <= profile.max_chars_per_line
        duration = cue.end_ms - cue.start_ms
        assert profile.min_duration_ms <= duration <= profile.max_duration_ms
        chars = len(" ".join(cue.lines))
        assert cue.word_count == 1 or chars / (duration / 1000) <= profile.max_cps
    for before, after in itertools.pairwise(cues):
        assert after.start_ms - before.end_ms >= profile.min_gap_ms


def test_no_preposition_split() -> None:
    """AC-4: no cue ends with a preposition, so a preposition is never separated from its word.
    The fixture is long enough that the builder must break inside it. Positive control: the
    fixture produces at least two cues."""
    cues_mod = _mod("transcribe_engine.domain.render.cues")
    normalize = _mod("transcribe_engine.domain.text").normalize
    base = ["كلمة", "في", "جملة", "طويلة", "على", "مدى", "ساعة", "من", "الوقت", "عن", "ناس", "مع"]
    words: list[tuple[str, int, int]] = []
    cursor = 0
    for _ in range(4):
        for text in base:
            words.append((text, cursor, cursor + 400))
            cursor += 450
    profile = cues_mod.SubtitleProfile(max_chars_per_line=18, max_lines=2)
    cues = cues_mod.build_cues(_transcript(words), profile)
    assert len(cues) >= 2
    prepositions = {normalize(p).search for p in PREPOSITIONS}
    for cue in cues:
        last_word = normalize(cue.lines[-1].rstrip(" ")).search.split()[-1]
        assert last_word not in prepositions
