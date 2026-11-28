"""RAG chunks, contextual headers and rank fusion (S18, design: الـ RAG). Pure domain logic.

- `split_sentences` groups sentences into chunks of at most `max_tokens`. A similarity drop between
  two sentences is a topic boundary: a chunk never holds sentences from both sides, and a boundary
  cut ignores the minimum size. Overlap (in sentences) is added only inside one topic.
- `build_rag_chunks` gives the small level: one sentence per segment for now (speaker turns are the
  unit the design names), with the metadata the source has. Similarities come from the embedder
  (S18 port); until then the caller passes none and no boundary is cut.
- `rrf` fuses ranked lists with reciprocal rank fusion (k = 60).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from transcribe_engine.domain.keys import rag_chunk_id
from transcribe_engine.domain.transcript import CanonicalTranscript, Segment

__all__ = [
    "RagChunk",
    "RagChunkConfig",
    "RagSentence",
    "build_rag_chunks",
    "contextual_header",
    "rrf",
    "split_sentences",
]

RRF_K = 60


@dataclass(frozen=True)
class RagSentence:
    text: str
    tokens: int
    start_ms: int
    end_ms: int
    segment_id: str
    speaker: str | None


@dataclass(frozen=True)
class RagChunkConfig:
    min_tokens: int = 200
    max_tokens: int = 400
    overlap_sentences: int = 1


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    transcript_id: str
    transcript_version: int
    media_id: str
    tenant_id: str
    acl: tuple[str, ...]
    start_ms: int
    end_ms: int
    segment_ids: tuple[str, ...]
    parent_id: str | None
    chapter_title: str | None
    speakers: tuple[str, ...]
    lang: str
    has_code_switch: bool
    entities: tuple[str, ...]
    confidence: float
    quality_flags: tuple[str, ...]
    media_title: str
    recorded_at: date | None
    text: str
    level: Literal["small", "parent", "summary"]


def split_sentences(
    sentences: Sequence[RagSentence],
    similarities: Sequence[float],
    boundary_below: float,
    cfg: RagChunkConfig,
) -> tuple[tuple[int, int], ...]:
    """Spans `(start, end)` over `sentences`, end exclusive. `similarities[i]` is the similarity
    between sentence i and i+1; a value below `boundary_below` is a topic boundary."""
    count = len(sentences)
    if count == 0:
        return ()

    def boundary_before(index: int) -> bool:
        return index > 0 and similarities[index - 1] < boundary_below

    spans: list[tuple[int, int]] = []
    start = 0
    tokens = 0
    index = 0
    while index < count:
        if index > start and boundary_before(index):
            # A topic boundary is never crossed, whatever the chunk size.
            spans.append((start, index))
            start, tokens = index, 0
            continue
        size = sentences[index].tokens
        if index > start and tokens + size > cfg.max_tokens:
            spans.append((start, index))
            back = max(start + 1, index - cfg.overlap_sentences)
            inside_topic = all(not boundary_before(k) for k in range(back + 1, index))
            if cfg.overlap_sentences and back < index and inside_topic:
                start = back
                tokens = sum(sentences[k].tokens for k in range(start, index))
            else:
                start, tokens = index, 0
            continue
        tokens += size
        index += 1
    spans.append((start, count))
    return _backfill_undersized(tuple(spans), sentences, boundary_before, cfg)


def _backfill_undersized(
    spans: tuple[tuple[int, int], ...],
    sentences: Sequence[RagSentence],
    boundary_before: Callable[[int], bool],
    cfg: RagChunkConfig,
) -> tuple[tuple[int, int], ...]:
    """Extend a span below `min_tokens` backwards over the sentences before it, while the span
    stays within `max_tokens` and no topic boundary is crossed. The extension overlaps the previous
    span, which the design allows (overlap, D-088). A span that cannot reach the minimum without
    passing the maximum or a boundary stays as it is: a short tail is kept, not dropped."""
    items = list(spans)

    def tokens(a: int, b: int) -> int:
        return sum(sentences[k].tokens for k in range(a, b))

    for idx, (a, b) in enumerate(items):
        start = a
        while (
            tokens(start, b) < cfg.min_tokens
            and start > 0
            and not boundary_before(start)
            and tokens(start - 1, b) <= cfg.max_tokens
        ):
            start -= 1
        items[idx] = (start, b)
    return tuple(items)


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> tuple[tuple[str, float], ...]:
    """Reciprocal rank fusion: each item scores 1/(k + rank) in each list it is in (rank from 1).

    Items come back by score, highest first; a tie goes to the item id that sorts first."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return tuple(sorted(scores.items(), key=lambda pair: (-pair[1], pair[0])))


def build_rag_chunks(
    transcript: CanonicalTranscript,
    *,
    tenant_id: str,
    tokenize: Callable[[str], int],
    cfg: RagChunkConfig,
    similarities: Sequence[float] | None = None,
    boundary_below: float = 0.0,
) -> tuple[RagChunk, ...]:
    """Small-level chunks for one transcript version, with the metadata the source provides.

    `similarities[i]` between sentence i and i+1 below `boundary_below` is a topic boundary. Without
    similarities no boundary is found (D-088)."""
    sentences = [_sentence(segment, tokenize) for segment in transcript.segments]
    sims = list(similarities) if similarities is not None else [1.0] * max(0, len(sentences) - 1)
    spans = split_sentences(sentences, sims, boundary_below=boundary_below, cfg=cfg)
    chunks: list[RagChunk] = []
    for start, end in spans:
        segments = transcript.segments[start:end]
        words = [word for segment in segments for word in segment.words]
        confidences = [w.conf for w in words if w.conf is not None]
        chunks.append(
            RagChunk(
                chunk_id=rag_chunk_id(
                    transcript.transcript_id,
                    transcript.version,
                    segments[0].start_ms,
                    segments[-1].end_ms,
                ),
                transcript_id=transcript.transcript_id,
                transcript_version=transcript.version,
                media_id=transcript.media.media_id,
                tenant_id=tenant_id,
                acl=(tenant_id,),
                start_ms=segments[0].start_ms,
                end_ms=segments[-1].end_ms,
                segment_ids=tuple(segment.id for segment in segments),
                parent_id=None,
                chapter_title=None,
                speakers=_speakers(segments),
                lang=transcript.media.language,
                has_code_switch=any(w.lang != transcript.media.language for w in words),
                entities=(),
                confidence=sum(confidences) / len(confidences) if confidences else 0.0,
                quality_flags=tuple(transcript.warnings),
                media_title="",
                recorded_at=None,
                text=" ".join(sentences[i].text for i in range(start, end)),
                level="small",
            )
        )
    return tuple(chunks)


def contextual_header(chunk: RagChunk) -> str:
    """Prepended to the text for embedding only, never shown to a reader."""
    title = chunk.media_title or chunk.media_id
    speakers = ", ".join(chunk.speakers) or "unknown"
    return f"{title} | speakers: {speakers} | {chunk.start_ms}-{chunk.end_ms} ms"


def _sentence(segment: Segment, tokenize: Callable[[str], int]) -> RagSentence:
    text = " ".join(word.text for word in segment.words)
    return RagSentence(
        text=text,
        tokens=tokenize(text),
        start_ms=segment.start_ms,
        end_ms=segment.end_ms,
        segment_id=segment.id,
        speaker=segment.speaker,
    )


def _speakers(segments: Sequence[Segment]) -> tuple[str, ...]:
    seen: list[str] = []
    for segment in segments:
        speaker = segment.speaker
        if speaker is not None and speaker not in seen:
            seen.append(speaker)
    return tuple(seen)
