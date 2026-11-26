"""S18 RAG chunking and fusion (pure domain): AC-1 token bounds (Hypothesis), AC-2 no chunk
crosses a topic boundary, AC-3 metadata complete, AC-4 RRF known ranking.

Each check has a positive control (a chunk that should exist does exist, a known score is returned),
so a splitter that returns nothing, or a fusion that returns a constant, cannot pass.
"""

import importlib
from types import ModuleType

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _sentence(index: int, tokens: int) -> object:
    rag = _mod("transcribe_engine.domain.rag")
    return rag.RagSentence(
        text=f"s{index}",
        tokens=tokens,
        start_ms=index * 1000,
        end_ms=index * 1000 + 900,
        segment_id=f"seg-{index}",
        speaker="SPEAKER_00",
    )


@pytest.mark.xfail(strict=True, reason="S18")
@settings(max_examples=200, deadline=None)
@given(
    token_counts=st.lists(st.integers(min_value=1, max_value=120), min_size=1, max_size=40),
    overlap=st.integers(min_value=0, max_value=2),
)
def test_chunks_within_token_bounds(token_counts: list[int], overlap: int) -> None:
    """AC-1: a chunk holds at most `max_tokens` unless one sentence alone is longer. Every sentence
    is covered. Positive control: the chunks cover all sentences (at least one chunk exists)."""
    rag = _mod("transcribe_engine.domain.rag")
    cfg = rag.RagChunkConfig(min_tokens=50, max_tokens=100, overlap_sentences=overlap)
    sentences = [_sentence(i, n) for i, n in enumerate(token_counts)]
    sims = [1.0] * (len(sentences) - 1)  # no topic boundary anywhere
    spans = rag.split_sentences(sentences, sims, boundary_below=0.0, cfg=cfg)
    assert spans
    assert spans[0][0] == 0
    assert spans[-1][1] == len(sentences)
    for start, end in spans:
        total = sum(token_counts[start:end])
        assert end > start
        assert total <= cfg.max_tokens or end - start == 1, (start, end, total)


@pytest.mark.xfail(strict=True, reason="S18")
def test_no_chunk_crosses_topic_boundary() -> None:
    """AC-2: a similarity drop between sentences 2 and 3 is a topic boundary; no chunk holds both.
    Positive control: without the drop the same sentences share a chunk."""
    rag = _mod("transcribe_engine.domain.rag")
    cfg = rag.RagChunkConfig(min_tokens=10, max_tokens=400, overlap_sentences=1)
    sentences = [_sentence(i, 20) for i in range(6)]
    drop = [0.9, 0.9, 0.1, 0.9, 0.9]  # similarity between i and i+1; 0.1 at i=2 is the boundary
    spans = rag.split_sentences(sentences, drop, boundary_below=0.3, cfg=cfg)
    for start, end in spans:
        assert not (start <= 2 and end >= 4), (start, end)
    assert len(spans) >= 2
    no_drop = rag.split_sentences(sentences, [0.9] * 5, boundary_below=0.3, cfg=cfg)
    assert any(start <= 2 and end >= 4 for start, end in no_drop)


@pytest.mark.xfail(strict=True, reason="S18")
def test_metadata_complete() -> None:
    """AC-3: every field the source provides is set on the chunk. Positive control: the confidence
    is the mean of the word confidences, not a constant."""
    rag = _mod("transcribe_engine.domain.rag")
    tr = _mod("transcribe_engine.domain.transcript")
    segments = (
        tr.Segment(
            id="seg-1",
            start_ms=0,
            end_ms=2000,
            speaker="SPEAKER_00",
            words=(tr.Word("مرحبا", 0, 500, "ar", 0.8), tr.Word("بكم", 500, 1000, "ar", 0.6)),
        ),
        tr.Segment(
            id="seg-2",
            start_ms=2000,
            end_ms=3000,
            speaker="SPEAKER_01",
            words=(tr.Word("hello", 2000, 2500, "en", 1.0),),
        ),
    )
    transcript = tr.CanonicalTranscript(
        schema_version="1",
        transcript_id="tr-1",
        version=3,
        source="asr",
        media=tr.MediaMeta(media_id="med-1", duration_ms=3000, language="ar"),
        provenance=tr.Provenance(engine="e", revision="r", pipeline_version="p", config_hash="c"),
        speakers=(tr.Speaker("SPEAKER_00", "A"), tr.Speaker("SPEAKER_01", "B")),
        segments=segments,
        events=(),
        warnings=(),
    )
    cfg = rag.RagChunkConfig(min_tokens=1, max_tokens=400, overlap_sentences=0)
    chunks = rag.build_rag_chunks(transcript, tenant_id="tenant-a", tokenize=lambda t: 1, cfg=cfg)
    assert chunks
    c = chunks[0]
    assert c.transcript_id == "tr-1"
    assert c.transcript_version == 3
    assert c.media_id == "med-1"
    assert c.tenant_id == "tenant-a"
    assert c.segment_ids
    assert c.speakers
    assert c.lang == "ar"
    assert c.text
    assert c.start_ms == 0
    assert c.confidence == pytest.approx((0.8 + 0.6 + 1.0) / 3)
    assert c.chunk_id
    assert c.level == "small"


@pytest.mark.xfail(strict=True, reason="S18")
def test_rrf_known_ranking() -> None:
    """AC-4: reciprocal rank fusion with k=60. `x` is first in two rankings and second in one.
    `y` is
    second in two rankings and absent from one. Positive control: scores are the exact sums."""
    rag = _mod("transcribe_engine.domain.rag")
    fused = rag.rrf([["x", "y"], ["y", "x"], ["x"]], k=60)
    assert [item for item, _ in fused] == ["x", "y"]
    scores = dict(fused)
    assert scores["x"] == pytest.approx(1 / 61 + 1 / 62 + 1 / 61)
    assert scores["y"] == pytest.approx(1 / 62 + 1 / 61)
