"""Chunk persistence port (S10): plan, per-chunk results, and the merged transcript.

The plan is written before any ASR call. A restarted job reads the same chunks and skips the
ones whose result exists (resume, AC-7). Every method takes the tenant id. RLS enforces
it too (D-024).
"""

from collections.abc import Sequence
from typing import Protocol

from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.merge import MergedWords, RawWord

__all__ = ["ChunkRepository"]


class ChunkRepository(Protocol):
    async def add_plan(self, tenant_id: str, job_id: str, chunks: Sequence[Chunk]) -> None:
        """Store the plan. A chunk id that is already stored is left unchanged (idempotent)."""
        ...

    async def is_prepared(self, tenant_id: str, job_id: str) -> bool:
        """True once the plan was committed, even an empty one (a silent file).

        The GPU stage waits for it (S10 fence).
        """
        ...

    async def plan(self, tenant_id: str, job_id: str) -> tuple[Chunk, ...]:
        """The plan in index order. Empty when none was stored."""
        ...

    async def save_result(
        self, tenant_id: str, job_id: str, chunk_id: str, words: tuple[RawWord, ...]
    ) -> None:
        """Store one chunk's ASR output as soon as it completes. Resume depends on it."""
        ...

    async def results(self, tenant_id: str, job_id: str) -> dict[str, tuple[RawWord, ...]]:
        """Stored results keyed by chunk id."""
        ...

    async def save_transcript(self, tenant_id: str, job_id: str, merged: MergedWords) -> None:
        """Store the merged transcript. Written once, in the same transaction as the completion."""
        ...

    async def transcript(self, tenant_id: str, job_id: str) -> MergedWords | None: ...
