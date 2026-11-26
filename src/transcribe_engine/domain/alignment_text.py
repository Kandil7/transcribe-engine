"""Text prepared for forced alignment (S14, design: 5. Forced Alignment). Pure domain logic.

The aligner needs the words as they are spoken. Digits become Egyptian spoken forms before
alignment (Q1: "50" is "خمسين"). The stored word keeps its original form, so the token map gives
each original token back with the spoken words it produced. Numbers from 1000 up are spelled out
digit by digit. English tokens are marked lang="en" so the aligner can use an English model or
interpolate their times from their neighbours.

The Arabic lexicon is the Egyptian form. A change of form changes alignment, so it is a decision
(D-047), measured in S16.
"""

from dataclasses import dataclass

__all__ = ["TokenMap", "verbalize_for_alignment"]

TRAILING_PUNCTUATION = ".،,؟?!:;"
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_UNITS = {
    0: "صفر",
    1: "واحد",
    2: "اتنين",
    3: "تلاتة",
    4: "أربعة",
    5: "خمسة",
    6: "ستة",
    7: "سبعة",
    8: "تمانية",
    9: "تسعة",
}
_TEENS = {
    10: "عشرة",
    11: "حداشر",
    12: "اتناشر",
    13: "تلتاشر",
    14: "أربعتاشر",
    15: "خمستاشر",
    16: "ستاشر",
    17: "سبعتاشر",
    18: "تمنتاشر",
    19: "تسعتاشر",
}
_TENS = {
    20: "عشرين",
    30: "تلاتين",
    40: "أربعين",
    50: "خمسين",
    60: "ستين",
    70: "سبعين",
    80: "تمانين",
    90: "تسعين",
}
_HUNDREDS = {
    1: "مية",
    2: "ميتين",
    3: "تلتمية",
    4: "أربعمية",
    5: "خمسمية",
    6: "ستمية",
    7: "سبعمية",
    8: "تمنمية",
    9: "تسعمية",
}


@dataclass(frozen=True)
class TokenMap:
    original: str  # the token as stored, punctuation included
    spoken: tuple[str, ...]  # the words aligned for it
    lang: str  # "ar" or "en"


def verbalize_for_alignment(text: str) -> tuple[str, tuple[TokenMap, ...]]:
    """Return the spoken text and one TokenMap per original token, in order."""
    spoken_words: list[str] = []
    maps: list[TokenMap] = []
    for token in text.split():
        core = token.rstrip(TRAILING_PUNCTUATION)
        if core and _is_number(core):
            spoken = _spoken_number(int(core.translate(_ARABIC_INDIC)))
        elif core:
            spoken = [core]
        else:
            spoken = []  # punctuation has no sound: it stays in the stored token only
        lang = "en" if _is_english(core) else "ar"
        maps.append(TokenMap(original=token, spoken=tuple(spoken), lang=lang))
        spoken_words.extend(spoken)
    return " ".join(spoken_words), tuple(maps)


def _is_number(core: str) -> bool:
    normalized = core.translate(_ARABIC_INDIC)
    return normalized.isascii() and normalized.isdigit()


def _is_english(core: str) -> bool:
    has_latin = any(ch.isascii() and ch.isalpha() for ch in core)
    has_arabic = any("؀" <= ch <= "ۿ" for ch in core)
    return has_latin and not has_arabic


def _spoken_number(value: int) -> list[str]:
    if value >= 1000:
        return [_UNITS[int(digit)] for digit in str(value)]
    if value < 100:
        return _under_hundred(value)
    hundreds, rest = divmod(value, 100)
    words = [_HUNDREDS[hundreds]]
    if rest:
        words.extend(_under_hundred(rest, joiner=True))
    return words


def _under_hundred(value: int, *, joiner: bool = False) -> list[str]:
    """Spoken words for 0 to 99. With a joiner, the first word gets the Arabic "و" prefix."""
    if value < 10:
        return [_prefixed(_UNITS[value], joiner)]
    if value < 20:
        return [_prefixed(_TEENS[value], joiner)]
    tens, units = divmod(value, 10)
    if units == 0:
        return [_prefixed(_TENS[value], joiner)]
    return [_prefixed(_UNITS[units], joiner), "و" + _TENS[tens * 10]]


def _prefixed(word: str, joiner: bool) -> str:
    return "و" + word if joiner else word
