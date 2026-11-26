"""Enricher port (S19, D-058). Each method is one artifact; a failure in one does not stop others.

The LLM-backed adapter waits for an owner decision (R-010). Until then the fake in tests/fakes is
the only implementation.
"""

from collections.abc import Sequence
from typing import Protocol

from transcribe_engine.domain.chapters import Chapter, TimedEntity

__all__ = ["Enricher"]


class Enricher(Protocol):
    async def chapters(self, text: str) -> Sequence[Chapter]:
        """Chapter titles and approximate times. Times are snapped to segments by the caller."""
        ...

    async def summary(self, text: str, max_words: int) -> str: ...

    async def entities(self, text: str) -> Sequence[TimedEntity]:
        """Named entities with approximate times.

        Entities not in the text are dropped by the caller."""
        ...
