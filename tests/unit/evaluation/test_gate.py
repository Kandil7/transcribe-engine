"""S16 regression gate (AC-6, dry run on a fake result): the gate fails when CER rises by more than
0.5 points over the stored baseline, and passes otherwise. Positive control: a result equal to the
baseline passes, so a gate that always fails cannot pass.
Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def test_gate_fails_on_cer_rise_over_half_a_point() -> None:
    gate = _mod("evaluation.gate")
    baseline = 0.0600
    assert gate.gate_passes(baseline, baseline) is True
    assert gate.gate_passes(baseline, 0.0650) is True  # exactly 0.5 points: not over the limit
    assert gate.gate_passes(baseline, 0.0660) is False  # 0.6 points: over the limit
    assert gate.gate_passes(baseline, 0.0400) is True  # an improvement always passes
