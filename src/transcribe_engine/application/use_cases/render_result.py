"""Render a completed job's result in any output format (S15, AC-8).

Every format is derived from the one stored transcript (ADR-0004). Subtitle profiles change only
the cue limits. The profile values for `youtube` and `social_vertical` are proposals (D-046),
tuned with a viewer test (S15 Q1). Renders are not cached yet; they are cheap pure functions of
the stored transcript, and the cache is a follow-up (D-046).
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from typing import Literal

from transcribe_engine.application.errors import (
    ResultNotAvailableError,
    ResultNotReadyError,
    UnsupportedFeatureError,
)
from transcribe_engine.application.ports.repositories import UnitOfWork
from transcribe_engine.application.use_cases.job_queries import GetJob
from transcribe_engine.domain.jobs import JobState
from transcribe_engine.domain.render.csv_ import render_csv
from transcribe_engine.domain.render.cues import SubtitleProfile, build_cues
from transcribe_engine.domain.render.md import render_md
from transcribe_engine.domain.render.srt import render_srt
from transcribe_engine.domain.render.txt import render_txt
from transcribe_engine.domain.render.vtt import render_vtt
from transcribe_engine.domain.transcript import (
    CanonicalTranscript,
    Provenance,
    to_json,
    transcript_from_merged,
)

__all__ = ["PROFILES", "RenderResult", "RenderedBody"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]

PROFILES: dict[str, SubtitleProfile] = {
    "broadcast": SubtitleProfile(),
    "youtube": SubtitleProfile(max_duration_ms=6000),
    "social_vertical": SubtitleProfile(max_chars_per_line=24, max_duration_ms=4000),
}
MEDIA_TYPES: dict[str, str] = {
    "canonical": "application/json",
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "srt": "application/x-subrip",
    "vtt": "text/vtt; charset=utf-8",
}


@dataclass(frozen=True)
class RenderedBody:
    content: bytes
    media_type: str


class RenderResult:
    def __init__(self, make_uow: MakeUow) -> None:
        self._make_uow = make_uow

    async def __call__(
        self,
        tenant_id: str,
        job_id: str,
        *,
        format: str,
        profile: str = "broadcast",
        numerals: Literal["western", "arabic_indic"] = "western",
    ) -> RenderedBody:
        if format not in MEDIA_TYPES or profile not in PROFILES:
            raise UnsupportedFeatureError
        job = await GetJob(self._make_uow)(tenant_id, job_id)
        if job.state != JobState.COMPLETED:
            raise ResultNotReadyError
        async with self._make_uow(tenant_id) as uow:
            merged = await uow.chunks.transcript(tenant_id, job_id)
        if merged is None:
            raise ResultNotAvailableError
        config = job.config
        transcript = transcript_from_merged(
            merged,
            transcript_id=job.id,
            media_id=job.media_id,
            language=config.language,
            provenance=Provenance(
                engine=config.engine,
                revision=config.model_revision,
                pipeline_version=config.pipeline_version,
                config_hash=config.config_hash(),
            ),
            warnings=tuple(job.warnings),
        )
        subtitles = replace(PROFILES[profile], numerals=numerals)
        return RenderedBody(_render(transcript, format, subtitles), MEDIA_TYPES[format])


def _render(transcript: CanonicalTranscript, format: str, subtitles: SubtitleProfile) -> bytes:
    if format == "canonical":
        return to_json(transcript)
    if format == "txt":
        return render_txt(transcript)
    if format == "md":
        return render_md(transcript)
    if format == "csv":
        return render_csv(transcript)
    cues = build_cues(transcript, subtitles)
    if format == "srt":
        return render_srt(cues)
    return render_vtt(cues).encode("utf-8")
