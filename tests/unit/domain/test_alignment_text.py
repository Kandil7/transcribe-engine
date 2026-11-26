"""S14 alignment text (AC-1 digits verbalized and mapped back, AC-2 English tokens marked).
Each rule has a positive control on the same function, so a function that changes nothing or
changes everything cannot pass. Imports happen inside helpers so the module collects before the
code exists.
"""

import importlib
from types import ModuleType


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _verbalize(text: str) -> tuple[str, object]:
    return _mod("transcribe_engine.domain.alignment_text").verbalize_for_alignment(text)


def test_digits_verbalized_and_mapped_back() -> None:
    """AC-1: '50 جنيه' is aligned as 'خمسين جنيه' (Egyptian form, Q1), and the token map returns
    the digits to the stored form '50'. Positive control: a text without digits is unchanged."""
    spoken, maps = _verbalize("50 جنيه")
    assert spoken == "خمسين جنيه"
    assert maps[0].original == "50"  # type: ignore[attr-defined]
    assert maps[0].spoken == ("خمسين",)  # type: ignore[attr-defined]
    assert maps[1].original == "جنيه"  # type: ignore[attr-defined]
    plain, plain_maps = _verbalize("جنيه واحد")
    assert plain == "جنيه واحد"
    assert [m.original for m in plain_maps] == ["جنيه", "واحد"]  # type: ignore[attr-defined]


def test_english_tokens_marked() -> None:
    """AC-2: an English token is marked lang='en'; Arabic tokens are lang='ar'. Positive control:
    the English token keeps its original text."""
    _, maps = _verbalize("عايز اكلم Ahmed دلوقتي")
    langs = {m.original: m.lang for m in maps}  # type: ignore[attr-defined]
    assert langs["Ahmed"] == "en"
    assert langs["عايز"] == "ar"
    assert [m.original for m in maps if m.lang == "en"] == ["Ahmed"]  # type: ignore[attr-defined]
