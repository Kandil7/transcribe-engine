"""Arabic text normalization for search, RAG and evaluation (S04, D-008..D-010).

The rules are a fixed character table in pure code. Each rule maps one character to one
character, or deletes it, so the offset map back to the raw text is exact. `raw` is never modified.
"""

import unicodedata
from dataclasses import dataclass

__all__ = ["NormalizedText", "fold_char", "map_span", "normalize"]

# Rules 1-3 and D-009: alef variants, alef maksura, teh marbuta, Persian yeh.
_LETTER_FOLDS: dict[str, str] = {
    "\u0623": "\u0627",  # أ → ا
    "\u0625": "\u0627",  # إ → ا
    "\u0622": "\u0627",  # آ → ا
    "\u0671": "\u0627",  # ٱ → ا
    "\u0649": "\u064a",  # ى → ي
    "\u0629": "\u0647",  # ة → ه
    "\u06cc": "\u064a",  # ی → ي (D-009)
}


def fold_char(ch: str) -> str:
    """Apply the 1:1 folding rules (1-3, 5, 7) to one character. Deletions are not applied here."""
    if ch in _LETTER_FOLDS:
        return _LETTER_FOLDS[ch]
    code = ord(ch)
    if 0x0660 <= code <= 0x0669:  # Arabic-Indic digits
        return chr(ord("0") + code - 0x0660)
    if 0x06F0 <= code <= 0x06F9:  # Eastern Arabic-Indic digits
        return chr(ord("0") + code - 0x06F0)
    # Rule 7 (D-010): lowercase Latin letters only, one character at a time, so offsets stay exact.
    if unicodedata.name(ch, "").startswith("LATIN "):
        lowered = ch.lower()
        if len(lowered) == 1:
            return lowered
    return ch


# Rule 4: tatweel and the diacritics U+064B-U+0652, U+0670 are deleted.
_DELETE = frozenset({0x0640, 0x0670, *range(0x064B, 0x0653)})


@dataclass(frozen=True)
class NormalizedText:
    raw: str
    search: str
    offsets: tuple[int, ...]  # offsets[i] is the index in `raw` of search[i]


def normalize(raw: str) -> NormalizedText:
    """Return the search text for `raw` with an exact offset map back to it."""
    chars: list[str] = []
    offsets: list[int] = []
    for index, ch in enumerate(raw):
        if ord(ch) in _DELETE:
            continue
        if ch.isspace():
            # Rule 6 (D-010): keep the first space of a run; drop the others and leading space.
            if not chars or chars[-1] == " ":
                continue
            chars.append(" ")
        else:
            chars.append(fold_char(ch))
        offsets.append(index)
    if chars and chars[-1] == " ":
        chars.pop()
        offsets.pop()
    return NormalizedText(raw=raw, search="".join(chars), offsets=tuple(offsets))


def map_span(n: NormalizedText, start: int, end: int) -> tuple[int, int]:
    """Map a search-text span [start, end) to a raw-text span (end exclusive)."""
    if not 0 <= start <= end <= len(n.search):
        raise ValueError("span out of range")
    if start == end:
        pos = n.offsets[start] if start < len(n.offsets) else len(n.raw)
        return pos, pos
    return n.offsets[start], n.offsets[end - 1] + 1
