"""Tests for src/score_wer.py — scorer math and slice window."""

from src.score_wer import (
    hypothesis_for,
    parse_reference,
    score,
    score_reference_lines,
)

MINI = {
    "video_id": "mini",
    "transcript_raw": "السلام عليكم ورحمة الله",
    "segments": [
        {"start": 0.0, "end": 10.0, "text": "السلام عليكم"},
        {"start": 10.0, "end": 20.0, "text": "ورحمة الله"},
    ],
}


def test_exact_match():
    m = score(MINI["transcript_raw"], MINI["transcript_raw"])
    assert m["wer"] == 0.0
    assert m["cer"] == 0.0
    assert m["ref_words"] == m["hyp_words"]


def test_one_substitution():
    m = score("السلام عليكم ورحمة الله", "السلام عليكم ورحمة الله")
    assert m["wer"] == 0.0
    m2 = score("السلام عليكم ورحمة الله", "السلام عليكم ورحمة ALLAH")
    assert m2["wer"] > 0.0 and m2["substitutions"] >= 1


def test_deletion_insertion():
    # ref has 4 words; hyp drops one (deletion), adds one (insertion)
    m = score("السلام ورحمة الله زائد", "السلام عليكم ورحمة الله")
    assert 0 < m["wer"] < 1.0
    assert m["deletions"] == 1
    assert m["insertions"] == 1


def test_slice_window():
    # only segments overlapping [10,20)
    hyp = hypothesis_for(MINI, (10.0, 20.0))
    assert hyp == "ورحمة الله"


def test_slice_overlap_boundary():
    # a segment spanning the cut is included when it overlaps
    d = {
        "video_id": "x",
        "segments": [
            {"start": 0.0, "end": 30.0, "text": "قطعة واحدة طويلة"},
        ],
    }
    assert hypothesis_for(d, (10.0, 20.0)) == "قطعة واحدة طويلة"
    assert hypothesis_for(d, (35.0, 40.0)) == ""


def test_normalization_folds():
    # hamzated alef + diacritics must not count as errors after fold
    ref = "إِنَّ اللهَ عَزَّ وَجَلَّ"
    hyp = "ان الله عز وجل"
    m = score(hyp, ref)
    assert m["wer"] == 0.0
    assert m["cer"] == 0.0


def test_parse_reference_plain():
    lines, flat = parse_reference("السلام عليكم\nورحمة الله")
    assert lines == []
    assert flat == "السلام عليكم\nورحمة الله"


def test_parse_reference_timestamped():
    lines, flat = parse_reference("[0:00.0-0:10.0] السلام\n[0:10.0-0:20.0] عليكم\n")
    assert [(a, b, t) for a, b, t in lines] == [
        (0.0, 10.0, "السلام"),
        (10.0, 20.0, "عليكم"),
    ]
    assert flat == "السلام عليكم"


def test_score_reference_lines_per_segment():
    rec = {
        "video_id": "x",
        "segments": [
            {"start": 0.0, "end": 10.0, "text": "السلام عليكم"},
            {"start": 10.0, "end": 20.0, "text": "ورحمة الله"},
        ],
    }
    lines = [(0.0, 10.0, "السلام عليكم"), (10.0, 20.0, "ورحمة هالله")]
    out = score_reference_lines(rec, lines)
    assert out[0]["wer"] == 0.0
    assert out[1]["wer"] > 0.0  # one substitution in line 2
    assert out[1]["substitutions"] == 1
