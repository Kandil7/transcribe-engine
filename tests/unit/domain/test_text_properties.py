"""Property tests for S04 — Arabic text normalization (S04 spec)."""

import importlib
from itertools import pairwise
from types import ModuleType

import pytest
from hypothesis import given
from hypothesis import strategies as st


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.text")


TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),  # no lone surrogates
    max_size=60,
)


@pytest.mark.xfail(strict=True, reason="S04")
@given(TEXT)
def test_idempotent(raw: str) -> None:
    """AC-2: normalizing the search text again changes nothing."""
    t = _mod()
    once = t.normalize(raw)
    assert t.normalize(once.search).search == once.search


@pytest.mark.xfail(strict=True, reason="S04")
@given(TEXT)
def test_offsets_point_to_source(raw: str) -> None:
    """AC-3: each search char comes from the raw char at its offset, folded by rules 1-3, 5, 7.

    For a search space (rule 6), the raw char must be whitespace (D-010).
    """
    t = _mod()
    n = t.normalize(raw)
    for i, ch in enumerate(n.search):
        src = raw[n.offsets[i]]
        if ch == " ":
            assert src.isspace()
        else:
            assert t.fold_char(src) == ch


@pytest.mark.xfail(strict=True, reason="S04")
@given(TEXT)
def test_offsets_monotonic(raw: str) -> None:
    """AC-5: offsets strictly increase, so every search char maps to a distinct raw position."""
    offsets = _mod().normalize(raw).offsets
    assert all(a < b for a, b in pairwise(offsets))
