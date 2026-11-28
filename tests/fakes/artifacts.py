"""In-memory artifact store for the S19 tests. Same key as the Postgres table, and the same tenant
scope: a tenant reads only its own rows."""

from dataclasses import dataclass, field

from transcribe_engine.domain.artifacts import Artifact, ArtifactKind

Key = tuple[str, str, int, str, str, str]


@dataclass
class FakeArtifactStore:
    rows: dict[Key, Artifact] = field(default_factory=dict)

    async def get(
        self,
        tenant_id: str,
        transcript_id: str,
        transcript_version: int,
        kind: ArtifactKind,
        model: str,
        model_version: str,
    ) -> Artifact | None:
        return self.rows.get(
            (tenant_id, transcript_id, transcript_version, kind, model, model_version)
        )

    async def put(self, tenant_id: str, artifact: Artifact) -> None:
        key = (
            tenant_id,
            artifact.transcript_id,
            artifact.transcript_version,
            artifact.kind,
            artifact.model,
            artifact.model_version,
        )
        self.rows[key] = artifact
