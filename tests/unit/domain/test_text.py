"""Acceptance tests for S04 — Arabic text normalization (specs/S04-arabic-text-normalization.md)."""

import importlib
import re
from pathlib import Path
from types import ModuleType

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "normalization_cases.tsv"


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.text")


def _unescape(cell: str) -> str:
    # Fixture cells use backslash escapes for tab, newline and \u-code points, so they stay visible.
    cell = cell.replace("\\t", "\t").replace("\\n", "\n")
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), cell)


def _cases() -> list[tuple[str, str]]:
    lines = FIXTURE.read_text(encoding="utf8").splitlines()[1:]
    rows = []
    for line in lines:
        raw, expected = line.split("\t", 1)
        rows.append((_unescape(raw), _unescape(expected)))
    return rows


def test_fixture_has_at_least_40_rows() -> None:
    assert len(_cases()) >= 40


@pytest.mark.parametrize(("raw", "expected"), _cases())
def test_cases_table(raw: str, expected: str) -> None:
    """AC-1: every row of the case table."""
    assert _mod().normalize(raw).search == expected


def test_raw_is_never_modified() -> None:
    raw = "  الجُنَيْه   نزل  "
    assert _mod().normalize(raw).raw == raw


@pytest.mark.xfail(strict=True, reason="S04")
@pytest.mark.xfail(strict=True, reason="S04")
def test_map_span_round_trip() -> None:
    """AC-4: a search hit on 'الجنيه' maps back to the full raw word with its diacritics."""
    t = _mod()
    n = t.normalize("الجُنَيْه نزل")
    hit = n.search.index("الجنيه")
    start, end = t.map_span(n, hit, hit + len("الجنيه"))
    assert n.raw[start:end] == "الجُنَيْه"


@pytest.mark.xfail(strict=True, reason="S04")
@pytest.mark.xfail(strict=True, reason="S04")
def test_span_on_deleted_char_maps_to_nearest_kept_neighbour() -> None:
    """A span that starts or ends on a deleted character maps to the nearest kept neighbour."""
    t = _mod()
    n = t.normalize("ab\u064bcd")  # diacritic between b and c is deleted
    start, end = t.map_span(n, 1, 3)  # search "bc"
    assert n.raw[start:end] == "b\u064bc"


@pytest.mark.xfail(strict=True, reason="S04")
@pytest.mark.xfail(strict=True, reason="S04")
def test_empty_span_is_allowed_and_out_of_range_rejected() -> None:
    t = _mod()
    n = t.normalize("abc")
    start, end = t.map_span(n, 1, 1)
    assert start == end
    with pytest.raises(ValueError, match="out of range"):
        t.map_span(n, 0, 99)
