"""Regression gate for the nightly evaluation (S16, AC-6). Offline only.

CER values are fractions (0.06 is 6 points). The gate fails when the current CER is more than
`MAX_CER_RISE` (0.5 points) above the stored baseline. A small tolerance absorbs float error, so a
rise of exactly 0.5 points passes.
"""

__all__ = ["MAX_CER_RISE", "gate_passes"]

MAX_CER_RISE = 0.005  # 0.5 points, as a fraction
_TOLERANCE = 1e-12


def gate_passes(baseline_cer: float, current_cer: float) -> bool:
    return current_cer - baseline_cer <= MAX_CER_RISE + _TOLERANCE
