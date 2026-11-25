"""Arabic text normalization for search, RAG and evaluation (S04, D-008..D-010).

The rules are a fixed character table in pure code. Each rule maps one character to one
character, or deletes it, so the offset map back to the raw text is exact. `raw` is never modified.
"""

import unicodedata

__all__ = ["fold_char"]

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
