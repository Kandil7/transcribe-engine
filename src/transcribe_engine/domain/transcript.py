"""Canonical transcript (S15, ADR-0004): the one versioned source every output renders from.

Stored fields are the schema (docs/schemas/transcript-1.0.json). `raw_text`, `search_text` and the
word offsets are derived from the words and never stored (design: التمثيل المرجعي). Times are
integer milliseconds (ADR-0003). The JSON form is canonical: sorted keys, no extra whitespace, so
the same transcript always gives the same bytes (AC-7).
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from transcribe_engine.domain.merge import MergedWords
from transcribe_engine.domain.merge import Word as MergedWord
from transcribe_engine.domain.text import NormalizedText, normalize

__all__ = [
    "CanonicalTranscript",
    "Event",
    "MediaMeta",
    "Provenance",
    "Segment",
    "Speaker",
    "Word",
    "from_json",
    "to_json",
    "transcript_from_merged",
]

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class Word:
    text: str
    start_ms: int
    end_ms: int
    lang: str
    conf: float | None


@dataclass(frozen=True)
class Segment:
    id: str
    start_ms: int
    end_ms: int
    speaker: str | None
    words: tuple[Word, ...]


@dataclass(frozen=True)
class Speaker:
    id: str
    label: str


@dataclass(frozen=True)
class MediaMeta:
    media_id: str
    duration_ms: int
    language: str


@dataclass(frozen=True)
class Provenance:
    engine: str
    revision: str
    pipeline_version: str
    config_hash: str


@dataclass(frozen=True)
class Event:
    kind: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class CanonicalTranscript:
    schema_version: str
    transcript_id: str
    version: int
    source: Literal["asr", "human"]
    media: MediaMeta
    provenance: Provenance
    speakers: tuple[Speaker, ...]
    segments: tuple[Segment, ...]
    events: tuple[Event, ...]
    warnings: tuple[str, ...]

    def _words(self) -> list[Word]:
        return [word for segment in self.segments for word in segment.words]

    def raw_text(self) -> str:
        """The words joined by single spaces, in order. Derived, never stored."""
        return " ".join(word.text for word in self._words())

    def word_offsets(self) -> tuple[tuple[int, int], ...]:
        """Character span of each word inside `raw_text()`, in word order."""
        spans: list[tuple[int, int]] = []
        cursor = 0
        for index, word in enumerate(self._words()):
            if index:
                cursor += 1  # the single space
            spans.append((cursor, cursor + len(word.text)))
            cursor += len(word.text)
        return tuple(spans)

    def search_text(self) -> NormalizedText:
        """Normalized raw text for search and RAG (domain.text.normalize only)."""
        return normalize(self.raw_text())


def to_json(transcript: CanonicalTranscript) -> bytes:
    body = {
        "schema_version": transcript.schema_version,
        "transcript_id": transcript.transcript_id,
        "version": transcript.version,
        "source": transcript.source,
        "media": {
            "media_id": transcript.media.media_id,
            "duration_ms": transcript.media.duration_ms,
            "language": transcript.media.language,
        },
        "provenance": {
            "engine": transcript.provenance.engine,
            "revision": transcript.provenance.revision,
            "pipeline_version": transcript.provenance.pipeline_version,
            "config_hash": transcript.provenance.config_hash,
        },
        "speakers": [{"id": s.id, "label": s.label} for s in transcript.speakers],
        "segments": [
            {
                "id": segment.id,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "speaker": segment.speaker,
                "words": [
                    {
                        "text": word.text,
                        "start_ms": word.start_ms,
                        "end_ms": word.end_ms,
                        "lang": word.lang,
                        "conf": word.conf,
                    }
                    for word in segment.words
                ],
            }
            for segment in transcript.segments
        ],
        "events": [
            {"kind": e.kind, "start_ms": e.start_ms, "end_ms": e.end_ms} for e in transcript.events
        ],
        "warnings": list(transcript.warnings),
    }
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def from_json(data: bytes) -> CanonicalTranscript:
    try:
        body: Mapping[str, Any] = json.loads(data.decode("utf-8"))
        return CanonicalTranscript(
            schema_version=str(body["schema_version"]),
            transcript_id=str(body["transcript_id"]),
            version=int(body["version"]),
            source=body["source"],
            media=MediaMeta(**body["media"]),
            provenance=Provenance(**body["provenance"]),
            speakers=tuple(Speaker(**s) for s in body["speakers"]),
            segments=tuple(_segment(s) for s in body["segments"]),
            events=tuple(Event(**e) for e in body["events"]),
            warnings=tuple(str(w) for w in body["warnings"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("not a canonical transcript") from exc


def transcript_from_merged(
    merged: MergedWords,
    *,
    transcript_id: str,
    media_id: str,
    language: str,
    provenance: Provenance,
    warnings: tuple[str, ...] = (),
) -> CanonicalTranscript:
    """Build the canonical transcript of a completed job from its merged words.

    One segment per chunk, in chunk order. Speakers and events are empty until diarization (S17)
    and enrichment (S19) exist. Times are already integer milliseconds.
    """
    groups: list[list[MergedWord]] = []
    for word in merged.words:
        if groups and groups[-1][-1].chunk_idx == word.chunk_idx:
            groups[-1].append(word)
        else:
            groups.append([word])
    segments = tuple(
        Segment(
            id=f"seg-{index}",
            start_ms=group[0].start_ms,
            end_ms=group[-1].end_ms,
            speaker=None,
            words=tuple(
                Word(text=w.text, start_ms=w.start_ms, end_ms=w.end_ms, lang=language, conf=w.conf)
                for w in group
            ),
        )
        for index, group in enumerate(groups)
    )
    duration = max((w.end_ms for w in merged.words), default=0)
    return CanonicalTranscript(
        schema_version=SCHEMA_VERSION,
        transcript_id=transcript_id,
        version=1,
        source="asr",
        media=MediaMeta(media_id=media_id, duration_ms=duration, language=language),
        provenance=provenance,
        speakers=(),
        segments=segments,
        events=(),
        warnings=warnings,
    )


def _segment(raw: Mapping[str, Any]) -> Segment:
    words: Sequence[Mapping[str, Any]] = raw["words"]
    return Segment(
        id=str(raw["id"]),
        start_ms=int(raw["start_ms"]),
        end_ms=int(raw["end_ms"]),
        speaker=raw["speaker"],
        words=tuple(Word(**word) for word in words),
    )
