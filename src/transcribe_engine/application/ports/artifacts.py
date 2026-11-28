"""Artifact store port (S19). Rows are keyed by transcript version, kind, model and model version.

`put` replaces the payload of an existing key, so a retried derivation writes the same row again.
"""

from typing import Protocol

from transcribe_engine.domain.artifacts import Artifact, ArtifactKind

__all__ = ["ArtifactStore"]


class ArtifactStore(Protocol):
    async def get(
        self,
        tenant_id: str,
        transcript_id: str,
        transcript_version: int,
        kind: ArtifactKind,
        model: str,
        model_version: str,
    ) -> Artifact | None: ...

    async def put(self, tenant_id: str, artifact: Artifact) -> None: ...
