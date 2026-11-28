"""In-memory embedder for the S18 tests.

Deterministic 1024-dimensional vectors. It counts the texts it is asked to embed, which
the re-index test asserts (AC-5)."""

from dataclasses import dataclass


@dataclass
class FakeEmbedder:
    model: str = "fake-embed"
    version: str = "1"
    texts_embedded: int = 0
    calls: int = 0

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        self.texts_embedded += len(texts)
        return [_vector(text) for text in texts]


def _vector(text: str) -> list[float]:
    """A unit-length vector, as the real embedder returns (the embedder contract checks it)."""
    seed = sum(ord(c) for c in text) % 97
    raw = [((seed + i) % 17) / 17.0 for i in range(1024)]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]
