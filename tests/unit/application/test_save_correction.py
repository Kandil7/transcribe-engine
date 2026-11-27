"""S22 saving a correction on fakes.

AC-1 unchanged words keep their times. AC-2 only the changed segment is re-aligned. AC-3 a stale
base version is refused (409).

Each check has a positive control: an unchanged word keeps its time, the other segment is untouched,
and a save on the current version succeeds.
"""

import importlib
from types import ModuleType
from typing import Any

import pytest

from tests.fakes.aligner import FakeAligner
from tests.fakes.versions import FakeVersionStore


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _base() -> Any:
    tr = _mod("transcribe_engine.domain.transcript")
    return tr.CanonicalTranscript(
        schema_version="1",
        transcript_id="tr-1",
        version=1,
        source="asr",
        media=tr.MediaMeta(media_id="med-1", duration_ms=2000, language="ar"),
        provenance=tr.Provenance(engine="e", revision="r", pipeline_version="p", config_hash="c"),
        speakers=(tr.Speaker("SPEAKER_00", "Ali"),),
        segments=(
            tr.Segment(
                "s1",
                0,
                190,
                "SPEAKER_00",
                (tr.Word("a", 0, 90, "ar", None), tr.Word("b", 100, 190, "ar", None)),
            ),
            tr.Segment(
                "s2",
                1000,
                1190,
                "SPEAKER_00",
                (tr.Word("c", 1000, 1090, "ar", None), tr.Word("d", 1100, 1190, "ar", None)),
            ),
        ),
        events=(),
        warnings=(),
    )


def _edit() -> Any:
    corrections = _mod("transcribe_engine.domain.corrections")
    return corrections.Edit(segment_id="s2", word_index_from=1, word_index_to=2, new_text="e")


@pytest.mark.xfail(strict=True, reason="S22")
async def test_unchanged_words_keep_times() -> None:
    """AC-1: after the save, every word that did not change keeps its old start and end.

    Positive control: the changed word has a new time from the aligner, and the save made version 2.
    """
    save = _mod("transcribe_engine.application.use_cases.save_correction")
    versions = FakeVersionStore()
    versions.seed(_base())
    new_version = await save.SaveCorrection(versions, FakeAligner())(
        "tenant-a", "tr-1", 1, (_edit(),), {}
    )
    assert new_version == 2
    latest = await versions.latest("tenant-a", "tr-1")
    assert latest is not None
    words = {w.text: (w.start_ms, w.end_ms) for s in latest.segments for w in s.words}
    assert words["a"] == (0, 90)
    assert words["b"] == (100, 190)
    assert words["c"] == (1000, 1090)  # unchanged in s2, keeps its time
    assert words["e"] == (1010, 1020)  # new word, timed by the aligner


@pytest.mark.xfail(strict=True, reason="S22")
async def test_changed_segment_realigned_only() -> None:
    """AC-2: only the segment that changed is sent to the aligner.

    Positive control: the call log names s2, so the aligner ran at all.
    """
    save = _mod("transcribe_engine.application.use_cases.save_correction")
    versions = FakeVersionStore()
    versions.seed(_base())
    aligner = FakeAligner()
    await save.SaveCorrection(versions, aligner)("tenant-a", "tr-1", 1, (_edit(),), {})
    assert aligner.calls == ["s2"]


@pytest.mark.xfail(strict=True, reason="S22")
async def test_stale_base_version_conflict() -> None:
    """AC-3: saving on a base version that is no longer the latest raises a conflict (409).

    Positive control: saving on the current version succeeds.
    """
    save = _mod("transcribe_engine.application.use_cases.save_correction")
    errors = _mod("transcribe_engine.application.errors")
    versions = FakeVersionStore()
    versions.seed(_base())
    use_case = save.SaveCorrection(versions, FakeAligner())
    await use_case("tenant-a", "tr-1", 1, (_edit(),), {})  # version 2 now exists

    with pytest.raises(errors.StaleVersionError):
        await use_case("tenant-a", "tr-1", 1, (_edit(),), {})
    assert await use_case("tenant-a", "tr-1", 2, (_edit(),), {}) == 3
