"""S09 admission rules (AC-1 and AC-2 policy, AC-3 limits): pure functions, no I/O.

Each refusal sits next to a positive control, so an always-refusing rule cannot pass.
Imports happen inside helpers so this module collects before the rules module exists.
"""

import importlib
from types import ModuleType

import pytest


def _rules() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.media_rules")


def _limits_3h() -> object:
    return _rules().IngestLimits()


@pytest.mark.xfail(strict=True, reason="S09")
@pytest.mark.parametrize(
    "format_name",
    ["mp3", "wav", "flac", "aac", "ogg", "mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm"],
)
def test_allowed_formats_are_admitted(format_name: str) -> None:
    rules = _rules()
    assert rules.admission_error(format_name, 1_000, 1_000, _limits_3h()) is None


@pytest.mark.xfail(strict=True, reason="S09")
@pytest.mark.parametrize("format_name", ["hls,applehttp", "concat", "image2", "sox"])
def test_playlists_and_other_formats_are_unsupported(format_name: str) -> None:
    rules = _rules()
    code = rules.admission_error(format_name, 1_000, 1_000, _limits_3h())
    assert code is rules.ErrorCode.UNSUPPORTED_FORMAT


@pytest.mark.xfail(strict=True, reason="S09")
def test_duration_at_the_limit_is_admitted_and_above_it_is_too_long() -> None:
    rules = _rules()
    limit = rules.IngestLimits().max_duration_ms
    assert rules.admission_error("mp3", limit, 1, _limits_3h()) is None
    assert rules.admission_error("mp3", limit + 1, 1, _limits_3h()) is rules.ErrorCode.TOO_LONG


@pytest.mark.xfail(strict=True, reason="S09")
def test_size_above_the_limit_is_too_large() -> None:
    rules = _rules()
    limit = rules.IngestLimits().max_size_bytes
    assert rules.admission_error("mp3", 1_000, limit, _limits_3h()) is None
    assert rules.admission_error("mp3", 1_000, limit + 1, _limits_3h()) is rules.ErrorCode.TOO_LARGE


@pytest.mark.xfail(strict=True, reason="S09")
def test_format_is_checked_before_duration() -> None:
    rules = _rules()
    too_long = rules.IngestLimits().max_duration_ms + 1
    code = rules.admission_error("hls,applehttp", too_long, 1, _limits_3h())
    assert code is rules.ErrorCode.UNSUPPORTED_FORMAT
