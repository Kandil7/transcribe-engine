"""In-memory versioned transcript store for the S22 tests.

Versions are kept per transcript id. `latest` returns the highest version.
`save` takes only the next version in order.
"""

from dataclasses import dataclass, field

from transcribe_engine.domain.transcript import CanonicalTranscript


@dataclass
class FakeVersionStore:
    versions: dict[str, list[CanonicalTranscript]] = field(default_factory=dict)

    def seed(self, transcript: CanonicalTranscript) -> None:
        self.versions.setdefault(transcript.transcript_id, []).append(transcript)

    async def latest(self, tenant_id: str, transcript_id: str) -> CanonicalTranscript | None:
        del tenant_id
        history = self.versions.get(transcript_id)
        return history[-1] if history else None

    async def save(self, tenant_id: str, transcript: CanonicalTranscript) -> None:
        del tenant_id
        history = self.versions.setdefault(transcript.transcript_id, [])
        assert transcript.version == len(history) + 1, "versions are saved in order"
        history.append(transcript)
