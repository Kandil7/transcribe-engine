"""Property tests for S04 — Arabic text normalization (S04 spec)."""

import importlib
import unicodedata
from itertools import pairwise
from types import ModuleType

from hypothesis import given
from hypothesis import strategies as st


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.text")


# Literal expectations for rules 1-3, 5 and 7 (not the implementation's helper).
LITERAL_FOLDS = {
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
    "ى": "ي",
    "ة": "ه",
    "ی": "ي",
}
DELETED_CHARS = "ـًٌٍَُِّْٰ"  # tatweel and diacritics (rule 4)
RULE_CHARS = [
    *LITERAL_FOLDS,
    *DELETED_CHARS,
    *"٠١٢٣٤٥٦٧٨٩",
    *"۰۱۲۳۴۵۶۷۸۹",
    *"ABCDEFGHIJKLMNOPQRSTUVWXYZ \t\n",
    "É",
    "İ",
    *"ÀÇßŒ",
]
TEXT = st.one_of(
    st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=60),
    st.text(alphabet=st.sampled_from(RULE_CHARS), max_size=60),
)
FORBIDDEN_IN_SEARCH = set(LITERAL_FOLDS) | set(DELETED_CHARS)


def _literal_fold(ch: str) -> str:
    if ch in LITERAL_FOLDS:
        return LITERAL_FOLDS[ch]
    if "٠" <= ch <= "٩":
        return chr(ord("0") + ord(ch) - 0x0660)
    if "۰" <= ch <= "۹":
        return chr(ord("0") + ord(ch) - 0x06F0)
    # Rule 7 (D-010): Latin letters lowercase when the result is one character.
    if unicodedata.name(ch, "").startswith("LATIN ") and len(ch.lower()) == 1:
        return ch.lower()
    return ch


@given(TEXT)
def test_idempotent(raw: str) -> None:
    """AC-2: normalizing the search text again changes nothing, and no rule char survives."""
    t = _mod()
    once = t.normalize(raw)
    assert t.normalize(once.search).search == once.search
    assert not (set(once.search) & FORBIDDEN_IN_SEARCH)


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
            assert _literal_fold(src) == ch


@given(TEXT)
def test_offsets_monotonic(raw: str) -> None:
    """AC-5: offsets strictly increase, so every search char maps to a distinct raw position."""
    offsets = _mod().normalize(raw).offsets
    assert all(a < b for a, b in pairwise(offsets))
