"""Offline tests for QA gates."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qa import qa_checks


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


def test_qa_lid_mismatch_flagged():
    flags = qa_checks(
        duration=30.0,
        raw="text",
        segments=_segs(),
        word_segments=[{"word": "w", "start": 0, "end": 1, "score": 1}],
        lid_lang="eng",
        expected_lang="ar",
    )
    assert "lid_mismatch" in flags


def test_qa_lid_match_and_absent_clean():
    common = dict(
        duration=30.0,
        raw="text",
        segments=_segs(),
        word_segments=[{"word": "w", "start": 0, "end": 1, "score": 1}],
    )
    assert qa_checks(**common, lid_lang="ara", expected_lang="ar") == []
    assert qa_checks(**common) == []  # lid not requested


def test_qa_lid_failed_flagged():
    flags = qa_checks(
        duration=30.0,
        raw="text",
        segments=_segs(),
        word_segments=[{"word": "w", "start": 0, "end": 1, "score": 1}],
        lid_status="failed",
    )
    assert "lid_failed" in flags


# --- qa_scores: numeric quality metrics ------------------------------------------

from qa import qa_scores


def test_scores_clean_video():
    segs = _segs()
    words = [{"word": "w", "start": 0.0, "end": 0.5, "score": 0.9} for _ in range(4)]
    m = qa_scores(30.0, "some text", segs, words)
    assert m["mean_word_score"] == 0.9
    assert m["speech_ratio"] == 1.0  # 3 segments x 10s over 30s duration
    assert m["empty_ratio"] == 0.0
    assert m["repeat_max"] == 0


def test_scores_no_alignment():
    # align skipped/failed: mean_word_score must be None, not 0
    m = qa_scores(30.0, "text", _segs(), [])
    assert m["mean_word_score"] is None


def test_scores_empty_inputs():
    m = qa_scores()
    assert m == {
        "mean_word_score": None,
        "speech_ratio": None,
        "empty_ratio": None,
        "repeat_max": 0,
        "arabic_ratio": None,
    }


def test_scores_arabic_ratio():
    assert qa_scores(30.0, "الحمد لله رب العالمين", [], [])["arabic_ratio"] == 1.0
    assert qa_scores(30.0, "hello world", [], [])["arabic_ratio"] == 0.0
    mixed = qa_scores(30.0, "الحمد hello", [], [])["arabic_ratio"]
    assert 0.0 < mixed < 1.0
    # digits and punctuation are not letters and don't dilute the ratio
    assert qa_scores(30.0, "الحمد 123 !!! لله", [], [])["arabic_ratio"] == 1.0


def test_scores_empty_segments_ratio():
    segs = _segs() + [{"start": 30.0, "end": 40.0, "text": "   "}]
    m = qa_scores(40.0, "text", segs, [])
    assert m["empty_ratio"] == round(1 / 4, 3)
    assert m["speech_ratio"] == 1.0


def test_scores_repeat_max():
    phrase = "عبارة مكررة هنا كثيرا في النص الكبير جدا اليوم"
    fill = "والكلام مواصل فيه دائما ما يحدث بين الحروف"
    raw = " ".join(f"{fill} {phrase}{i % 3}" for i in range(40))
    m = qa_scores(600.0, raw, [], [])
    assert m["repeat_max"] >= 40  # the fixed filler repeats every iteration


def test_scores_schema_backcompat():
    from schema import VideoRecord

    old = VideoRecord(video_id="x", video_title="t")
    line = old.to_jsonl()  # dataclass built before qa_scores existed
    assert "qa_scores" not in line or json.loads(line)["qa_scores"] == {}
    rec = VideoRecord.from_jsonl(line)
    assert rec.qa_scores == {}
    d = VideoRecord.from_jsonl(
        json.dumps({**json.loads(line), "qa_scores": {"repeat_max": 31}})
    )
    assert d.qa_scores == {"repeat_max": 31}
