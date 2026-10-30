"""Tests for src/viewer.py — pure helpers only, no streamlit runtime."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from viewer import flatten_segments, load_records, record_status

RECORD = {
    "video_id": "abc123",
    "video_title": "درس",
    "duration": 120.4,
    "align_status": "ok",
    "qa": ["short_audio"],
    "lid_lang": "ara",
    "lid_confidence": 0.97,
    "qa_scores": {
        "mean_word_score": 0.93,
        "speech_ratio": 1.0,
        "empty_ratio": 0.0,
        "repeat_max": 31,
    },
    "timings": {"download": 12.3, "transcribe": 44.6, "total": 60.1},
    "segments": [
        {"start": 0.1, "end": 5.6, "text": "الحمد لله", "words": [1, 2]},
        {"start": 5.6, "end": 9.9, "text": "ليلة وليلة", "words": []},
    ],
    "word_segments": [1, 2, 3, 4, 5],
}


def test_load_records(tmp_path):
    p = tmp_path / "v.jsonl"
    p.write_text(json.dumps(RECORD) + "\n\n", encoding="utf-8")
    recs = load_records(p)
    assert len(recs) == 1
    assert recs[0]["video_id"] == "abc123"


def test_load_records_missing(tmp_path):
    assert load_records(tmp_path / "nope.jsonl") == []


def test_flatten_segments():
    rows = flatten_segments(RECORD)
    assert len(rows) == 2
    assert rows[0] == {
        "start": 0.1,
        "end": 5.6,
        "speaker": "",
        "text_raw": "الحمد لله",
        "word_count": 2,
    }
    # no words in segment: falls back to whitespace split of text
    assert rows[1]["word_count"] == 2


def test_record_status_chips():
    s = record_status(RECORD)
    assert s["qa"] == "short_audio"
    assert s["align"] == "ok"
    assert s["dl_s"] == 12
    assert s["asr_s"] == 45
    assert s["total_s"] == 60
    assert s["segments"] == 2 and s["words"] == 5
    assert s["mean_word_score"] == 0.93
    assert s["lid"] == "ara (0.97)"


def test_record_status_no_lid():
    s = record_status(dict(RECORD, lid_lang="", lid_confidence=0.0))
    assert s["lid"] == ""


def test_record_status_clean_and_empty_timing():
    r = dict(RECORD, qa=[], timings=None)
    s = record_status(r)
    assert s["qa"] == "clean"
    assert s["dl_s"] == s["asr_s"] == s["total_s"] == 0


def test_streamlit_importable():
    # the UI module imports streamlit at module load; smoke-check it
    import streamlit  # noqa: F401
