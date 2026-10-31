"""Offline tests for src/make_reference.py — pure helpers, no network."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from make_reference import (
    assign_to_segments,
    format_template,
    parse_vtt_words,
)

VTT = """WEBVTT
Kind: captions
Language: ar

00:00:00.080 --> 00:00:03.389 align:start position:100%

????<00:00:00.240><c> ?????</c><00:00:01.280><c> ????</c>

00:00:03.389 --> 00:00:05.950 align:start position:100%
context<00:00:03.600><c> ??</c><00:00:04.400><c> ????</c>
"""

SEGS = [
    {"start": 0.0, "end": 2.0, "text": "s0"},
    {"start": 2.0, "end": 6.0, "text": "s1"},
]


def test_parse_vtt_words_extracts_tagged_only():
    words = parse_vtt_words(VTT)
    # only tagged words count (untagged context lines are rolling duplicates)
    assert [w for _, w in words] == ["?????", "????", "??", "????"]
    assert words[0][0] == 0.24
    assert words[2][0] == 3.6


def test_assign_to_segments_by_time():
    words = parse_vtt_words(VTT)
    texts = assign_to_segments(words, SEGS)
    assert texts[0] == "????? ????"  # 0.24s and 1.28s
    assert texts[1] == "?? ????"  # 3.6s and 4.4s


def test_assign_nearest_for_outliers():
    texts = assign_to_segments([(99.0, "late")], SEGS)
    assert texts == ["", "late"]  # nearest is the last segment


def test_assign_empty_inputs():
    assert assign_to_segments([], SEGS) == ["", ""]
    assert assign_to_segments([(0.0, "x")], []) == []


def test_format_template_lines():
    texts = assign_to_segments(parse_vtt_words(VTT), SEGS)
    out = format_template(SEGS, texts)
    lines = out.strip().splitlines()
    assert lines[0] == "[0:00.0-0:02.0] ????? ????"
    assert lines[1].startswith("[0:02.0-0:06.0] ")
