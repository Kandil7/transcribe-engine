"""S22 training manifest (pure).

AC-5: only consented segments are exported.
AC-6: each line has exactly the seven spec fields, with the right values.

Each check has a positive control: a consented, confident segment is exported, and a
corrected segment is exported even below the confidence threshold.
"""

import importlib
from dataclasses import asdict
from types import ModuleType
from typing import Any


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _segment(sid: str, start: int, conf: float) -> Any:
    tr = _mod("transcribe_engine.domain.transcript")
    return tr.Segment(
        sid,
        start,
        start + 1000,
        "SPEAKER_00",
        (
            tr.Word("a", start, start + 500, "ar", conf),
            tr.Word("b", start + 500, start + 1000, "ar", conf),
        ),
    )


def _items() -> list[Any]:
    training = _mod("transcribe_engine.domain.training")
    return [
        training.TrainingSegment(
            _segment("s1", 0, 0.9), "audio/a.wav", "asr", 18.5, "ar", True, False
        ),
        training.TrainingSegment(
            _segment("s2", 2000, 0.9), "audio/b.wav", "asr", 18.5, "ar", False, False
        ),
        training.TrainingSegment(
            _segment("s3", 4000, 0.2), "audio/c.wav", "asr", 12.0, "ar", True, False
        ),
        training.TrainingSegment(
            _segment("s4", 6000, 0.2), "audio/d.wav", "human", None, "ar", True, True
        ),
    ]


def test_consent_required() -> None:
    """AC-5: segments without consent are never exported.

    Positive control: the consented, confident segment is exported, and a corrected segment is
    exported below the threshold.
    """
    training = _mod("transcribe_engine.domain.training")
    lines = list(training.export_manifest(_items(), min_conf=0.5))
    keys = {(line.audio, line.offset_ms) for line in lines}
    assert ("audio/a.wav", 0) in keys
    assert ("audio/d.wav", 6000) in keys
    assert all(line.audio != "audio/b.wav" for line in lines)
    assert all(line.audio != "audio/c.wav" for line in lines)


def test_manifest_fields() -> None:
    """AC-6: a line has exactly the spec's fields, and the values come from the segment and item."""
    training = _mod("transcribe_engine.domain.training")
    line = next(
        line
        for line in training.export_manifest(_items(), min_conf=0.5)
        if line.audio == "audio/a.wav"
    )
    assert set(asdict(line)) == {
        "audio",
        "offset_ms",
        "duration_ms",
        "text",
        "source",
        "snr_db",
        "lang",
    }
    assert line.offset_ms == 0
    assert line.duration_ms == 1000
    assert line.text == "a b"
    assert line.source == "asr"
    assert line.snr_db == 18.5
    assert line.lang == "ar"
