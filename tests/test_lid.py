"""Offline tests for src/lid.py — pure helpers, no transformers/torch."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lid import clip_window, lid_codes_equal  # noqa: E402


def test_clip_window_short_audio():
    assert clip_window(10.0, 30.0) == (0.0, 10.0)
    assert clip_window(0.0, 30.0) == (0.0, 0.0)


def test_clip_window_middle_slice():
    t0, t1 = clip_window(100.0, 30.0)
    assert t0 == 35.0 and t1 == 65.0  # centered
    assert t1 - t0 == 30.0


def test_clip_window_exact_length():
    assert clip_window(30.0, 30.0) == (0.0, 30.0)


def test_codes_equal_iso1_vs_iso3():
    assert lid_codes_equal("ar", "ara")
    assert lid_codes_equal("en", "eng")
    assert lid_codes_equal("ara", "ara")  # same code passes too
    assert not lid_codes_equal("ar", "eng")
    assert not lid_codes_equal("fr", "deu")


def test_codes_equal_empty_never_flags():
    assert lid_codes_equal("", "ara")
    assert lid_codes_equal("ar", "")
    assert lid_codes_equal("", "")
