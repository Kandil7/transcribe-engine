"""Offline tests for QA gates."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qa import qa_checks  # noqa: E402


def _segs(n=3, start=0.0, step=10.0):
    return [
        {"start": start + i * step, "end": start + (i + 1) * step, "text": f"seg {i}"}
        for i in range(n)
    ]


def test_qa_clean():
    segs = _segs()
    words = [{"word": "w", "start": 0.0, "end": 0.5, "score": 0.9}]
    assert (
        qa_checks(duration=30.0, raw="some text", segments=segs, word_segments=words)
        == []
    )


def test_qa_empty():
    flags = qa_checks(duration=30.0, raw="   ", segments=[], word_segments=[])
    assert "empty_transcript" in flags
    assert "no_segments" in flags


def test_qa_align_fallback_flagged():
    flags = qa_checks(
        duration=30.0,
        raw="text",
        segments=_segs(),
        word_segments=[],
        align_status="segment_only",
    )
    assert "align_segment_only" in flags


def test_qa_duration_mismatch():
    flags = qa_checks(
        duration=1000.0,
        raw="text",
        segments=_segs(n=2),
        word_segments=[{"word": "w", "start": 0, "end": 1, "score": 1}],
    )
    assert "duration_mismatch" in flags


def test_qa_bad_timestamps():
    flags = qa_checks(
        duration=10.0,
        raw="text",
        segments=[{"start": 5.0, "end": 2.0, "text": "x"}],
        word_segments=[{"word": "w", "start": 2, "end": 5, "score": 1}],
    )
    assert "bad_timestamps" in flags


def test_qa_short_audio():
    assert "short_audio" in qa_checks(duration=3.0, raw="hi", segments=_segs(n=1))
