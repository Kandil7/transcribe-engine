"""S15 determinism (AC-7): the same transcript renders to the same bytes on every call. Imports
happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType

import pytest

from tests.unit.render.test_srt import two_speaker_transcript

pytestmark = pytest.mark.xfail(strict=True, reason="S15")


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def test_byte_identical() -> None:
    cues_mod = _mod("transcribe_engine.domain.render.cues")
    srt = _mod("transcribe_engine.domain.render.srt")
    vtt = _mod("transcribe_engine.domain.render.vtt")
    serial = _mod("transcribe_engine.domain.transcript")
    transcript = two_speaker_transcript()
    profile = cues_mod.SubtitleProfile()
    assert serial.to_json(transcript) == serial.to_json(two_speaker_transcript())
    cues = cues_mod.build_cues(transcript, profile)
    assert cues == cues_mod.build_cues(two_speaker_transcript(), profile)
    assert srt.render_srt(cues) == srt.render_srt(cues)
    assert vtt.render_vtt(cues, speakers=True) == vtt.render_vtt(cues, speakers=True)
