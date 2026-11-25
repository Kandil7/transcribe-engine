"""Acceptance tests for S03 — time units (specs/S03-pipeline-config-and-keys.md, ADR-0003)."""

import importlib
from types import ModuleType

from hypothesis import given
from hypothesis import strategies as st


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.time")


def test_sample_rate_is_16khz() -> None:
    assert _mod().SAMPLE_RATE == 16_000


def test_samples_to_ms_floors() -> None:
    t = _mod()
    assert t.samples_to_ms(16) == 1
    assert t.samples_to_ms(15) == 0
    assert t.samples_to_ms(31_999) == 1_999


@given(ms=st.integers(min_value=0, max_value=10_000_000))
def test_round_trip_ms_samples(ms: int) -> None:
    """AC-5: ms → samples → ms is exact at 16 kHz (16 samples per ms)."""
    t = _mod()
    assert t.samples_to_ms(t.ms_to_samples(ms)) == ms
