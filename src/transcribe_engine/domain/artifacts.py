"""Derived artifacts of a transcript version (S19, design: artifacts). Pure data.

An artifact is identified by its transcript version, its kind, and the model and model version that
produced it. It never changes the transcript (S19 AC-4). The payload is JSON-compatible.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

__all__ = ["Artifact", "ArtifactKind"]

ArtifactKind = Literal["chapters", "summary", "entities", "analytics", "questions"]


@dataclass(frozen=True)
class Artifact:
    transcript_id: str
    transcript_version: int
    kind: ArtifactKind
    model: str
    model_version: str
    payload: Mapping[str, object]
