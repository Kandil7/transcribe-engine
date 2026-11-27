"""S14 (R-005, D-070): CTC Viterbi forced alignment on pure Python, no numpy in the domain.

Each target token must be placed on the frames where the model emits it. Positive controls: clean
logits give the expected spans, a repeated token keeps a blank between its two spans, and too few
frames are refused instead of guessed.
"""

import importlib
from types import ModuleType

import pytest

BLANK = 0


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.ctc")


def _frames(emitted: list[int], vocab: int = 3) -> list[list[float]]:
    """One row per frame: the emitted symbol is near 0 (log-probability), the rest -10."""
    return [[0.0 if v == e else -10.0 for v in range(vocab)] for e in emitted]


@pytest.mark.xfail(strict=True, reason="S14")
def test_tokens_are_placed_on_their_frames() -> None:
    ctc = _mod()
    emitted = [BLANK, 1, 1, BLANK, 2, 2]
    spans = ctc.ctc_viterbi(_frames(emitted), [1, 2], BLANK)
    assert spans == ((1, 2), (4, 5))


@pytest.mark.xfail(strict=True, reason="S14")
def test_repeated_token_needs_a_blank_between_spans() -> None:
    ctc = _mod()
    emitted = [1, 1, BLANK, 1, 1]
    assert ctc.ctc_viterbi(_frames(emitted), [1, 1], BLANK) == ((0, 1), (3, 4))


@pytest.mark.xfail(strict=True, reason="S14")
def test_too_few_frames_is_refused() -> None:
    ctc = _mod()
    with pytest.raises(ValueError, match="too few frames"):
        ctc.ctc_viterbi(_frames([1]), [1, 2], BLANK)
