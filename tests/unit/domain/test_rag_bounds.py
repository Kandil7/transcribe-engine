"""S18 AC-1 and AC-2, the cases the first RAG tests do not reach (review findings, S18).

- A tail below min_tokens is extended backwards while it stays within max_tokens (D-088).
- The extension never crosses a topic boundary (AC-2).
- build_rag_chunks honours the boundary threshold it is given, and finds the boundary in its input.

Each check has a positive control: the case is built so the merge or the boundary is the only thing
that changes the outcome.
"""

import importlib
from dataclasses import replace
from types import ModuleType

from transcribe_engine.domain.rag import RagChunkConfig


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _sentences(tokens: list[int]) -> list[object]:
    rag = _mod("transcribe_engine.domain.rag")
    return [
        rag.RagSentence(
            text=f"s{i}",
            tokens=t,
            start_ms=i * 1000,
            end_ms=i * 1000 + 900,
            segment_id=f"seg-{i}",
            speaker=None,
        )
        for i, t in enumerate(tokens)
    ]


def test_undersized_tail_is_extended_backwards_within_the_maximum() -> None:
    """Tokens [300, 150, 30, 90, 260, 40, 40] with no boundary: the splitter's last span is (5, 7),
    80 tokens, below 200. Extending it back to sentence 4 gives 340 tokens, within 400, so the tail
    becomes (4, 7). Positive control: without the back-fill the last span is (5, 7)."""
    rag = _mod("transcribe_engine.domain.rag")
    cfg = RagChunkConfig()
    tokens = [300, 150, 30, 90, 260, 40, 40]
    spans = rag.split_sentences(_sentences(tokens), [1.0] * 6, boundary_below=0.0, cfg=cfg)
    assert spans == ((0, 1), (1, 4), (3, 6), (4, 7))


def test_backfill_never_crosses_a_topic_boundary() -> None:
    """Tokens [300, 150, 30] with a boundary before sentence 1. The 180-token tail may not extend
    back over that boundary, so it stays (1, 3). Extending it would also pass 400 tokens."""
    rag = _mod("transcribe_engine.domain.rag")
    cfg = RagChunkConfig()
    sents = _sentences([300, 150, 30])
    spans = rag.split_sentences(sents, [0.1, 0.9], boundary_below=0.5, cfg=cfg)
    assert spans == ((0, 1), (1, 3))


def test_no_chunk_exceeds_the_maximum_after_the_backfill() -> None:
    """Every span stays within max_tokens, and the spans still cover the whole transcript."""
    rag = _mod("transcribe_engine.domain.rag")
    cfg = RagChunkConfig()
    tokens = [300, 150, 30, 90, 260, 40, 40]
    spans = rag.split_sentences(_sentences(tokens), [1.0] * 6, boundary_below=0.0, cfg=cfg)
    assert spans[0][0] == 0
    assert spans[-1][1] == len(tokens)
    for start, end in spans:
        assert sum(tokens[k] for k in range(start, end)) <= cfg.max_tokens


def test_build_rag_chunks_splits_at_a_boundary_it_is_given() -> None:
    """A transcript of three segments (300, 150, 30 words), with a boundary between the first two.
    Positive control: the chunks follow the boundary, so the first chunk is the first segment alone,
    and the other two segments form the second chunk (the tail may not join the head)."""
    merge = _mod("transcribe_engine.domain.merge")
    transcript = _mod("transcribe_engine.domain.transcript")
    rag = _mod("transcribe_engine.domain.rag")
    words: list[object] = []
    for chunk_idx, count in enumerate([300, 150, 30]):
        for _ in range(count):
            n = len(words)
            words.append(merge.Word(f"w{n}", n * 100, n * 100 + 90, None, chunk_idx))
    merged = merge.MergedWords(words=tuple(words), sample_rate=16_000)
    provenance = transcript.Provenance(
        engine="whisper-local", revision="rev", pipeline_version="1.0.0", config_hash="c" * 64
    )
    built = transcript.transcript_from_merged(
        merged,
        transcript_id="job-bound",
        media_id="media-bound",
        language="ar",
        provenance=provenance,
    )
    built = replace(built, version=1)
    chunks = rag.build_rag_chunks(
        built,
        tenant_id="tenant-a",
        tokenize=lambda text: len(text.split()),
        cfg=RagChunkConfig(),
        similarities=[0.1, 0.9],
        boundary_below=0.5,
    )
    assert [c.segment_ids for c in chunks] == [("seg-0",), ("seg-1", "seg-2")]
