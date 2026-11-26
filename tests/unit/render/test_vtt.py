"""S15 WebVTT renderer (AC-5 golden with speakers). The expected text is written out by hand.
Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType

import pytest

from tests.unit.render.test_srt import two_speaker_transcript

GOLDEN = (
    "WEBVTT\n\n"
    "00:00:00.000 --> 00:00:01.800\n<v SPEAKER_01>\u200fمرحبا بيكم في البرنامج.\u200f\n\n"
    "00:00:02.000 --> 00:00:03.500\n<v SPEAKER_02>\u200fأهلا بيك يا أستاذ\n\n"
)

pytestmark = pytest.mark.xfail(strict=True, reason="S15")


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def test_golden_speakers() -> None:
    """AC-5: the WebVTT with voice tags matches the hand-written golden text exactly. Positive
    control: the two cues carry different speaker tags, so a renderer that drops the tags fails."""
    cues_mod = _mod("transcribe_engine.domain.render.cues")
    vtt = _mod("transcribe_engine.domain.render.vtt")
    cues = cues_mod.build_cues(two_speaker_transcript(), cues_mod.SubtitleProfile())
    assert vtt.render_vtt(cues, speakers=True) == GOLDEN
