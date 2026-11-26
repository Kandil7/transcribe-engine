"""S13 routing policy (AC-1 one case per table row, AC-2 clean audio has no steps). Each row has a
clean positive control on the same profile, so a policy that always returns the same plan cannot
pass. Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from dataclasses import replace
from types import ModuleType
from typing import Any

import pytest

RATE = 16_000


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _clean() -> Any:
    routing = _mod("transcribe_engine.domain.routing")
    return routing.AudioProfile(
        snr_db=30.0,
        c50_db=25.0,
        music_ratio=0.0,
        speech_ratio=0.8,
        overlap_ratio=0.0,
        clipping_ratio=0.0,
        loudness_lufs=-23.0,
        source_sample_rate=RATE,
        channels=1,
        quality_mos=4.0,
    )


def _plan(profile: Any) -> Any:
    routing = _mod("transcribe_engine.domain.routing")
    return routing.plan_processing(profile, routing.RoutingPolicy())


def _steps(plan: Any) -> set[str]:
    return {str(step) for step in plan.steps}


@pytest.mark.xfail(strict=True, reason="S13")
def test_clean_audio_has_no_steps() -> None:
    """AC-2: clean audio gets no steps, no flags, original audio for ASR, nothing skipped."""
    plan = _plan(_clean())
    assert plan.steps == ()
    assert plan.flags == frozenset()
    assert plan.feed_asr == "original"
    assert plan.skip_asr is False


@pytest.mark.xfail(strict=True, reason="S13")
@pytest.mark.parametrize(
    ("row", "changes", "expected_steps", "expected_flags", "feed_asr", "skip_asr"),
    [
        ("clean SNR above 15", {"snr_db": 15.5}, set(), set(), "original", False),
        ("medium noise", {"snr_db": 10.0}, {"Denoise"}, set(), "original", False),
        ("heavy noise", {"snr_db": 4.9}, set(), {"low_snr"}, "original", False),
        ("music under speech", {"music_ratio": 0.31}, {"SeparateVocals"}, set(), "enhanced", False),
        (
            "music, no speech",
            {"music_ratio": 0.5, "speech_ratio": 0.0},
            set(),
            {"music", "no_speech"},
            "original",
            True,
        ),
        ("reverb", {"c50_db": 5.0}, set(), {"reverb"}, "original", False),
        ("telephony", {"source_sample_rate": 8000}, set(), {"telephony"}, "original", False),
        ("stereo", {"channels": 2}, {"SplitChannels"}, set(), "original", False),
        ("overlap", {"overlap_ratio": 0.2}, set(), {"overlap"}, "original", False),
        ("quiet", {"loudness_lufs": -40.0}, {"Loudnorm"}, set(), "enhanced", False),
        ("clipping", {"clipping_ratio": 0.02}, set(), {"clipping"}, "original", False),
        ("no speech", {"speech_ratio": 0.01}, set(), {"no_speech"}, "original", True),
    ],
)
def test_policy_table(
    row: str,
    changes: dict[str, Any],
    expected_steps: set[str],
    expected_flags: set[str],
    feed_asr: str,
    skip_asr: bool,
) -> None:
    profile = replace(_clean(), **changes)
    plan = _plan(profile)
    assert _steps(plan) == expected_steps, row
    assert set(plan.flags) == expected_flags, row
    assert plan.feed_asr == feed_asr, row
    assert plan.skip_asr is skip_asr, row
