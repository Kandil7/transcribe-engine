"""S15 canonical JSON (AC-1 round trip and schema, AC-2 derived search text and offsets).
Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
import json
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema
from hypothesis import given, settings
from hypothesis import strategies as st

SCHEMA = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "transcript-1.0.json"
ARABIC = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _sample(words: list[tuple[str, int, int]] | None = None) -> Any:
    t = _mod("transcribe_engine.domain.transcript")
    if words is None:
        words = [
            ("مرحبا", 0, 500),
            ("بيكم", 500, 900),
            ("في", 900, 1100),
            ("البرنامج.", 1100, 1800),
        ]
    segment = t.Segment(
        id="seg-1",
        start_ms=words[0][1],
        end_ms=words[-1][2],
        speaker="S1",
        words=tuple(
            t.Word(text=w, start_ms=s, end_ms=e, lang="ar", conf=None) for w, s, e in words
        ),
    )
    return t.CanonicalTranscript(
        schema_version="1.0",
        transcript_id="tr-1",
        version=1,
        source="asr",
        media=t.MediaMeta(media_id="media-1", duration_ms=words[-1][2], language="ar"),
        provenance=t.Provenance(
            engine="vllm", revision="rev-1", pipeline_version="1.0.0", config_hash="c" * 64
        ),
        speakers=(t.Speaker(id="S1", label="SPEAKER_01"),),
        segments=(segment,),
        events=(),
        warnings=(),
    )


@settings(max_examples=50, deadline=None)
@given(st.lists(st.text(alphabet=ARABIC, min_size=1, max_size=8), min_size=1, max_size=20))
def test_round_trip_and_schema_valid(texts: list[str]) -> None:
    """AC-1: to_json then from_json gives the same transcript, and the JSON matches the schema."""
    serial = _mod("transcribe_engine.domain.transcript")
    words = [(text, i * 100, i * 100 + 90) for i, text in enumerate(texts)]
    original = _sample(words)
    data = serial.to_json(original)
    assert serial.from_json(data) == original
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(json.loads(data), schema)


def test_search_text_derived_from_words() -> None:
    """AC-2: search_text is the normalized raw_text, offsets map each word back to the raw text,
    and the JSON stores neither derived field. Positive control: each offset slice equals its
    word."""
    serial = _mod("transcribe_engine.domain.transcript")
    normalize = _mod("transcribe_engine.domain.text").normalize
    transcript = _sample()
    raw = transcript.raw_text()
    assert raw == "مرحبا بيكم في البرنامج."
    assert transcript.search_text() == normalize(raw)
    offsets = transcript.word_offsets()
    for word, (start, end) in zip(transcript.segments[0].words, offsets, strict=True):
        assert raw[start:end] == word.text
    body = json.loads(serial.to_json(transcript))
    assert "raw_text" not in body
    assert "search_text" not in body
    assert replace(transcript, version=2).raw_text() == raw
