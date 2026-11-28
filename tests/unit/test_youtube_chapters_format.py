"""S19 AC-6 (unit): the YouTube chapter lines.

Positive control: three chapters give three lines, the first at 00:00. Negative control: fewer than
three chapters is refused (422), as YouTube requires.
"""

import importlib
from types import ModuleType

import pytest

from transcribe_engine.application.errors import ChaptersTooFewError
from transcribe_engine.domain.chapters import Chapter


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.presentation.api.routes_results")


def test_three_chapters_give_three_lines_starting_at_zero() -> None:
    text = _mod()._youtube_text(
        (
            Chapter("مقدمة", 0, 40_000),
            Chapter("الفصل الأول", 43_000, 90_000),
            Chapter("ختام", 95_000, 120_000),
        )
    )
    assert text.splitlines() == ["00:00 مقدمة", "00:43 الفصل الأول", "01:35 ختام"]


def test_fewer_than_three_chapters_is_refused() -> None:
    with pytest.raises(ChaptersTooFewError):
        _mod()._youtube_text((Chapter("a", 0, 1_000), Chapter("b", 2_000, 3_000)))


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        (0, "00:00"),
        (59_999, "00:59"),
        (61_000, "01:01"),
        (3_599_000, "59:59"),
        (3_600_000, "1:00:00"),
    ],
)
def test_time_uses_minutes_then_hours(ms: int, expected: str) -> None:
    assert _mod()._youtube_time(ms) == expected
