"""Augmentation for the robustness matrix (S16): mix noise into speech at a target SNR.

Offline only. Samples are floats in this module because it runs on the evaluation set, not in the
pipeline (integer time rules apply to the pipeline only). The noise is scaled so the power ratio
of the signal to the scaled noise is exactly the target, measured over the whole signal.
"""

import math
from collections.abc import Sequence

__all__ = ["mix", "scale_noise", "snr_db"]


def _power(samples: Sequence[float]) -> float:
    if not samples:
        raise ValueError("cannot measure the power of an empty signal")
    return sum(x * x for x in samples) / len(samples)


def snr_db(signal: Sequence[float], noise: Sequence[float]) -> float:
    """10·log10(P_signal / P_noise) over the length of the signal."""
    length = len(signal)
    return 10 * math.log10(_power(signal) / _power(noise[:length]))


def scale_noise(signal: Sequence[float], noise: Sequence[float], target_db: float) -> list[float]:
    """Scale the noise so that snr_db(signal, scaled) equals target_db. Noise is cut to the
    signal's length."""
    length = len(signal)
    gain = math.sqrt(_power(signal) / (_power(noise[:length]) * 10 ** (target_db / 10)))
    return [gain * x for x in noise[:length]]


def mix(signal: Sequence[float], noise: Sequence[float], target_db: float) -> list[float]:
    scaled = scale_noise(signal, noise, target_db)
    return [s + n for s, n in zip(signal, scaled, strict=True)]
