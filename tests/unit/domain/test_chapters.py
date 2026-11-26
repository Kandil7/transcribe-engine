"""S19 chapters (pure): AC-2 chapter times snap to segment boundaries, never to LLM-invented times,
and entities must appear in the transcript text.

Positive control: an intro chapter gets a start at a real segment start, a chapter whose snapped
end is not after its start is dropped, and an entity that does appear is kept.
"""

import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


@pytest.mark.xfail(strict=True, reason="S19")
def test_times_snap_to_segments() -> None:
    """AC-2: off-grid chapter times snap to the nearest segment start (starts) or end (ends)."""
    chapters = _mod("transcribe_engine.domain.chapters")
    tr = _mod("transcribe_engine.domain.transcript")
    segments = (
        tr.Segment("s1", 0, 1900, None, ()),
        tr.Segment("s2", 2000, 3900, None, ()),
        tr.Segment("s3", 4000, 5900, None, ()),
        tr.Segment("s4", 6000, 7900, None, ()),
    )
    raw = (
        chapters.Chapter("intro", 130, 2100),
        chapters.Chapter("middle", 2350, 5800),
        chapters.Chapter("empty", 5900, 5950),  # snaps to start 6000, end 5900: dropped
    )
    out = chapters.snap_chapters(raw, segments)
    assert [c.title for c in out] == ["intro", "middle"]
    assert (out[0].start_ms, out[0].end_ms) == (0, 1900)
    assert (out[1].start_ms, out[1].end_ms) == (2000, 5900)


@pytest.mark.xfail(strict=True, reason="S19")
def test_entities_must_appear_in_text() -> None:
    """AC-3 (domain part): an entity whose text is not a substring of the transcript is dropped and
    counted. Positive control: an entity that does appear is kept."""
    chapters = _mod("transcribe_engine.domain.chapters")
    kept, dropped = chapters.verify_entities(
        (chapters.TimedEntity("القاهرة", 0), chapters.TimedEntity("Atlantis", 1000)),
        "ذهبنا إلى القاهرة أمس",
    )
    assert [e.text for e in kept] == ["القاهرة"]
    assert dropped == 1
