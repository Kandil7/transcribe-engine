"""S12 hallucination filter (AC-5): flags, never deletes. Each refusal is paired with a positive
control (normal text is not flagged), so a filter that flags everything cannot pass.

Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType
from typing import Any

RATE = 16_000
KNOWN = "اشتركوا في القناة"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _flag(texts_and_seconds: list[tuple[str, float]]) -> list[Any]:
    hallucination = _mod("transcribe_engine.domain.hallucination")
    segments = []
    cursor = 0
    for text, seconds in texts_and_seconds:
        end = cursor + round(seconds * RATE)
        segments.append(hallucination.RawSegment(text, cursor, end, RATE))
        cursor = end
    rules = hallucination.HallucinationRules(known_phrases=frozenset({KNOWN}))
    return list(hallucination.flag_hallucinations(segments, rules))


def test_repetition_flagged() -> None:
    phrase = "والله ده كان حاجة حلوة قوي "
    flagged = _flag([(phrase * 4, 8.0)])
    assert flagged[0].suspect is True
    assert "repetition" in flagged[0].reasons


def test_known_phrase_flagged() -> None:
    flagged = _flag([("كلام عادي " + KNOWN + " يا جماعة", 4.0)])
    assert flagged[0].suspect is True
    assert "known_phrase" in flagged[0].reasons


def test_fast_speech_flagged() -> None:
    # 30 words in 2 seconds is 15 words per second, above the 6 words/s limit.
    text = " ".join(f"كلمة{i}" for i in range(30))
    flagged = _flag([(text, 2.0)])
    assert flagged[0].suspect is True
    assert "fast_speech" in flagged[0].reasons


def test_normal_text_not_flagged() -> None:
    text = "ازيك يا أستاذ محمد عامل إيه النهارده في الشغل"  # 9 words in 5 seconds
    flagged = _flag([(text, 5.0)])
    assert len(flagged) == 1
    assert flagged[0].suspect is False
    assert flagged[0].reasons == ()
