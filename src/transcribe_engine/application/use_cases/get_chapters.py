"""Chapters of a transcript's latest version (S19, AC-6), derived by rule (D-081) and stored.

The first request for a version derives the chapters from the pauses and stores them. A later
request reads the stored artifact, so a rule version gives the same result under the same key. A
new rule version is a new `MODEL_VERSION`, so a new row (the old one stays readable).
"""

from dataclasses import dataclass
from typing import cast

from transcribe_engine.application.errors import TranscriptNotFoundError
from transcribe_engine.application.ports.artifacts import ArtifactStore
from transcribe_engine.application.ports.versions import TranscriptVersions
from transcribe_engine.domain.artifacts import Artifact
from transcribe_engine.domain.chapters import Chapter, rule_chapters

__all__ = ["ChaptersResult", "GetChapters"]


@dataclass(frozen=True)
class ChaptersResult:
    version: int
    chapters: tuple[Chapter, ...]


def _from_payload(payload: object) -> tuple[Chapter, ...] | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("chapters")
    if not isinstance(raw, list):
        return None
    chapters: list[Chapter] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            return None
        title, start, end = item.get("title"), item.get("start_ms"), item.get("end_ms")
        if not (isinstance(title, str) and isinstance(start, int) and isinstance(end, int)):
            return None
        chapters.append(Chapter(title, start, end))
    return tuple(chapters)


class GetChapters:
    MODEL = "rule-chapters"
    MODEL_VERSION = "1"

    def __init__(self, versions: TranscriptVersions, artifacts: ArtifactStore) -> None:
        self._versions = versions
        self._artifacts = artifacts

    async def __call__(self, tenant_id: str, job_id: str) -> ChaptersResult:
        transcript = await self._versions.latest(tenant_id, job_id)
        if transcript is None:
            raise TranscriptNotFoundError
        stored = await self._artifacts.get(
            tenant_id, job_id, transcript.version, "chapters", self.MODEL, self.MODEL_VERSION
        )
        chapters = _from_payload(stored.payload) if stored is not None else None
        if chapters is None:
            chapters = rule_chapters(transcript.segments)
            await self._artifacts.put(
                tenant_id,
                Artifact(
                    transcript_id=job_id,
                    transcript_version=transcript.version,
                    kind="chapters",
                    model=self.MODEL,
                    model_version=self.MODEL_VERSION,
                    payload={
                        "chapters": [
                            {"title": c.title, "start_ms": c.start_ms, "end_ms": c.end_ms}
                            for c in chapters
                        ]
                    },
                ),
            )
        return ChaptersResult(version=transcript.version, chapters=chapters)
