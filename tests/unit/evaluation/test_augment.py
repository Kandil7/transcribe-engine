"""S16 augmentation (AC-4): a mix at a target SNR measures within ±0.5 dB of that target. Positive
control: a different target gives a different measured SNR, so the scaling is really applied.
Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
import math
from types import ModuleType

import pytest

pytestmark = pytest.mark.xfail(strict=True, reason="S16")


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _signal() -> list[float]:
    return [math.sin(2 * math.pi * 220 * n / 16_000) * 0.5 for n in range(16_000)]


def _noise() -> list[float]:
    state = 12345
    values = []
    for _ in range(16_000):
        state = (1103515245 * state + 12345) % 2**31
        values.append(state / 2**31 * 2 - 1)
    return values


def test_snr_mix_exact() -> None:
    """AC-4: for targets 20, 10, 5 and 0 dB, the measured SNR of the mix is within 0.5 dB."""
    augment = _mod("evaluation.augment")
    signal, noise = _signal(), _noise()
    for target in (20.0, 10.0, 5.0, 0.0):
        scaled_noise = augment.scale_noise(signal, noise, target)
        measured = augment.snr_db(signal, scaled_noise)
        assert abs(measured - target) <= 0.5, target
    low = augment.snr_db(signal, augment.scale_noise(signal, noise, 0.0))
    high = augment.snr_db(signal, augment.scale_noise(signal, noise, 20.0))
    assert high - low == pytest.approx(20.0, abs=0.5)
