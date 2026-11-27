"""S22 version diff (pure): AC-4 known cases.

Each case has a positive control: identical versions have no changes, so a diff that reports
everything as changed cannot pass.
"""

import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _version(words: tuple[str, ...], speaker_label: str = "Ali") -> object:
    tr = _mod("transcribe_engine.domain.transcript")
    word_objs = tuple(
        tr.Word(text=w, start_ms=i * 100, end_ms=i * 100 + 90, lang="ar", conf=None)
        for i, w in enumerate(words)
    )
    return tr.CanonicalTranscript(
        schema_version="1",
        transcript_id="tr-1",
        version=1,
        source="asr",
        media=tr.MediaMeta(media_id="med-1", duration_ms=1000, language="ar"),
        provenance=tr.Provenance(engine="e", revision="r", pipeline_version="p", config_hash="c"),
        speakers=(tr.Speaker("SPEAKER_00", speaker_label),),
        segments=(tr.Segment("s1", 0, 1000, "SPEAKER_00", word_objs),),
        events=(),
        warnings=(),
    )


@pytest.mark.xfail(strict=True, reason="S22")
def test_diff_known_cases() -> None:
    """AC-4: replace, insert, delete and a renamed speaker are each reported once.

    Each change carries the before and after text. Positive control: identical versions have no
    changes.
    """
    diffing = _mod("transcribe_engine.domain.diff")
    base = _version(("x", "y", "z"))

    same = diffing.diff_versions(base, _version(("x", "y", "z")))
    assert same.word_changes == ()
    assert same.speaker_renames == ()

    replaced = diffing.diff_versions(base, _version(("x", "Y", "z")))
    assert [(c.kind, c.before, c.after) for c in replaced.word_changes] == [
        ("replace", ("y",), ("Y",))
    ]

    inserted = diffing.diff_versions(base, _version(("x", "y", "new", "z")))
    assert [(c.kind, c.before, c.after) for c in inserted.word_changes] == [
        ("insert", (), ("new",))
    ]

    deleted = diffing.diff_versions(base, _version(("x", "z")))
    assert [(c.kind, c.before, c.after) for c in deleted.word_changes] == [("delete", ("y",), ())]

    renamed = diffing.diff_versions(base, _version(("x", "y", "z"), speaker_label="Mona"))
    assert renamed.speaker_renames == (("SPEAKER_00", "Ali", "Mona"),)
