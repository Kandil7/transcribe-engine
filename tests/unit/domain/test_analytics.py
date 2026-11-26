"""S19 speaker analytics (pure): AC-1 talk time, speech rate, turns and silence.

Positive control: both speakers appear, and the rate is computed from the talk time, not zero.
"""

import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _transcript() -> object:
    tr = _mod("transcribe_engine.domain.transcript")

    def seg(sid: str, start: int, end: int, speaker: str, n_words: int) -> object:
        step = (end - start) // n_words
        words = tuple(
            tr.Word(f"w{i}", start + i * step, start + (i + 1) * step, "ar", None)
            for i in range(n_words)
        )
        return tr.Segment(id=sid, start_ms=start, end_ms=end, speaker=speaker, words=words)

    return tr.CanonicalTranscript(
        schema_version="1",
        transcript_id="tr-1",
        version=1,
        source="asr",
        media=tr.MediaMeta(media_id="med-1", duration_ms=8500, language="ar"),
        provenance=tr.Provenance(engine="e", revision="r", pipeline_version="p", config_hash="c"),
        speakers=(tr.Speaker("SPEAKER_00", "A"), tr.Speaker("SPEAKER_01", "B")),
        segments=(
            seg("s1", 0, 4000, "SPEAKER_00", 8),
            seg("s2", 4000, 6000, "SPEAKER_01", 4),
            seg("s3", 6500, 8500, "SPEAKER_00", 4),
        ),
        events=(),
        warnings=(),
    )


@pytest.mark.xfail(strict=True, reason="S19")
def test_talk_time_and_rate() -> None:
    """AC-1: talk time is the sum of a speaker's segment durations; the rate is words per minute of
    talk time; silence is the time with no speech.

    Positive control: SPEAKER_01 has its own numbers."""
    analytics = _mod("transcribe_engine.domain.analytics")
    result = analytics.speaker_analytics(_transcript())
    by = {s.speaker: s for s in result.speakers}
    assert by["SPEAKER_00"].talk_ms == 6000
    assert by["SPEAKER_00"].words == 12
    assert by["SPEAKER_00"].words_per_minute == pytest.approx(120.0)
    assert by["SPEAKER_00"].turns == 2
    assert by["SPEAKER_01"].talk_ms == 2000
    assert by["SPEAKER_01"].turns == 1
    assert result.silence_ms == 500
