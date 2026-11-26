"""S19 enrichment use case on a fake enricher: AC-3 entities verified against the text, AC-4 the
transcript bytes are unchanged, AC-5 one failing artifact does not stop the others.

Each check has a positive control (a verified entity is kept, the failing artifact is the only one
reported as failed, the other artifacts are present).
"""

import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _fake(**kwargs: object) -> object:
    return _mod("tests.fakes.enricher").FakeEnricher(**kwargs)


def _transcript() -> object:
    tr = _mod("transcribe_engine.domain.transcript")
    return tr.CanonicalTranscript(
        schema_version="1",
        transcript_id="tr-1",
        version=1,
        source="asr",
        media=tr.MediaMeta(media_id="med-1", duration_ms=2000, language="ar"),
        provenance=tr.Provenance(engine="e", revision="r", pipeline_version="p", config_hash="c"),
        speakers=(tr.Speaker("SPEAKER_00", "A"),),
        segments=(
            tr.Segment(
                "s1",
                0,
                2000,
                "SPEAKER_00",
                (
                    tr.Word("ذهبنا", 0, 500, "ar", None),
                    tr.Word("إلى", 500, 800, "ar", None),
                    tr.Word("القاهرة", 800, 1500, "ar", None),
                ),
            ),
        ),
        events=(),
        warnings=(),
    )


@pytest.mark.xfail(strict=True, reason="S19")
async def test_entities_verified_against_text() -> None:
    """AC-3: an entity that is not in the transcript is dropped and counted. Positive control: the
    entity that is in the transcript is returned."""
    chapters = _mod("transcribe_engine.domain.chapters")
    enrich = _mod("transcribe_engine.application.use_cases.enrich_transcript")
    fake = _fake(
        entities_out=(
            chapters.TimedEntity("القاهرة", 800),
            chapters.TimedEntity("Atlantis", 1000),
        )
    )
    result = await enrich.EnrichTranscript(fake).enrich(_transcript())
    assert result.entities == ("القاهرة",)
    assert result.dropped_entities == 1


@pytest.mark.xfail(strict=True, reason="S19")
async def test_transcript_unchanged() -> None:
    """AC-4: enrichment never changes the transcript; its canonical bytes are unchanged.

    Positive control: enrichment ran (the fake was called)."""
    enrich = _mod("transcribe_engine.application.use_cases.enrich_transcript")
    tr = _mod("transcribe_engine.domain.transcript")
    t = _transcript()
    before = tr.to_json(t)
    fake = _fake()
    await enrich.EnrichTranscript(fake).enrich(t)
    assert tr.to_json(t) == before
    assert fake.calls


@pytest.mark.xfail(strict=True, reason="S19")
async def test_one_failure_does_not_block_others() -> None:
    """AC-5: a failing chapters step is reported; the summary and entities still come back.
    Positive control: without the failure, nothing is reported as failed."""
    enrich = _mod("transcribe_engine.application.use_cases.enrich_transcript")
    failing = _fake(
        fail={"chapters": _mod("transcribe_engine.domain.errors").PermanentError("model refused")}
    )
    result = await enrich.EnrichTranscript(failing).enrich(_transcript())
    assert result.failures == ("chapters",)
    assert result.summary == "ملخص"
    assert result.chapters == ()

    working = _fake()
    ok = await enrich.EnrichTranscript(working).enrich(_transcript())
    assert ok.failures == ()
