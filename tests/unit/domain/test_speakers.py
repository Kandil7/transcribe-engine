"""S17 speaker assignment (pure domain): AC-1 max-overlap assignment, AC-2 overlap flag.

Each refusal has a positive control: a word fully inside one turn gets that speaker and no overlap
flag, so an assignment that always returns the same speaker cannot pass.
"""

import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _word(text: str, start: int, end: int) -> object:
    merge = _mod("transcribe_engine.domain.merge")
    return merge.Word(text=text, start_ms=start, end_ms=end, conf=None, chunk_idx=0)


def _turn(speaker: str, start: int, end: int) -> object:
    speakers = _mod("transcribe_engine.domain.speakers")
    return speakers.SpeakerTurn(speaker=speaker, start_ms=start, end_ms=end)


@pytest.mark.xfail(strict=True, reason="S17")
def test_max_overlap_assignment() -> None:
    """AC-1: a word takes the speaker with the largest time overlap. Positive control: a word fully
    inside one turn gets that turn's speaker."""
    speakers = _mod("transcribe_engine.domain.speakers")
    turns = [_turn("SPEAKER_00", 0, 1_000), _turn("SPEAKER_01", 1_000, 2_000)]
    words = [
        _word("inside", 100, 400),  # fully in SPEAKER_00
        _word("mostly_one", 900, 1_300),  # 100 ms of SPEAKER_00, 300 ms of SPEAKER_01
    ]
    out = speakers.assign_speakers(words, turns)
    assert [w.speaker for w in out] == ["SPEAKER_00", "SPEAKER_01"]


@pytest.mark.xfail(strict=True, reason="S17")
def test_overlap_flag() -> None:
    """AC-2: a word that overlaps speech of two speakers is flagged; a word inside one turn is not,
    and a word outside every turn has no speaker."""
    speakers = _mod("transcribe_engine.domain.speakers")
    turns = [_turn("SPEAKER_00", 0, 1_000), _turn("SPEAKER_01", 800, 2_000)]
    words = [
        _word("alone", 100, 400),  # only SPEAKER_00
        _word("crossing", 850, 950),  # both speakers overlap
        _word("silence", 5_000, 5_200),  # no turn at all
    ]
    out = speakers.assign_speakers(words, turns)
    assert out[0].speaker == "SPEAKER_00"
    assert out[0].overlap is False
    assert out[1].overlap is True
    assert out[2].speaker is None
    assert out[2].overlap is False
