"""JSONL contract for Transcribe Engine v1 (stdlib only, no heavy deps)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class WordSegment:
    word: str
    start: float
    end: float
    score: float = 0.0


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)


@dataclass
class VideoRecord:
    """One video = one JSONL line. Idempotent on video_id."""

    video_id: str
    video_title: str
    channel: str = ""
    channel_id: str = ""
    upload_date: str = ""  # YYYY-MM-DD or ""
    playlist_url: str = ""
    source_url: str = ""
    duration: float = 0.0
    language: str = "ar"
    license: str = ""
    model: str = "CohereLabs/cohere-transcribe-arabic-07-2026"
    align_status: str = "ok"  # ok | segment_only | skipped
    transcript_raw: str = ""
    transcript_norm: str = ""
    norm_version: str = "v1"
    qa: list = field(default_factory=list)  # QA flag strings, [] = clean
    qa_scores: dict = field(default_factory=dict)  # numeric quality metrics
    diarize_status: str = ""  # ok | failed | "" (not requested)
    speakers: list = field(default_factory=list)  # speaker labels, [] = none
    lid_status: str = ""  # ok | failed | "" (not requested)
    lid_lang: str = ""  # ISO 639-3 detection (ara, eng, ...)
    lid_confidence: float = 0.0
    dialect_status: str = ""  # ok | failed | "" (not requested)
    dialect: str = ""  # MAGHREB | LEV | MSA | GLF | EGY
    dialect_confidence: float = 0.0
    timings: dict = field(default_factory=dict)  # download/transcribe seconds
    segments: list = field(default_factory=list)
    word_segments: list = field(default_factory=list)
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @staticmethod
    def from_jsonl(line: str) -> VideoRecord:
        from dataclasses import MISSING

        d = json.loads(line)
        kwargs = {}
        for k, f in VideoRecord.__dataclass_fields__.items():
            if k in d:
                kwargs[k] = d[k]
            elif f.default is not MISSING:
                kwargs[k] = f.default
            elif f.default_factory is not MISSING:  # type: ignore[misc]
                kwargs[k] = f.default_factory()  # type: ignore[misc]
            else:
                kwargs[k] = ""
        return VideoRecord(**kwargs)
