"""Scripted enricher for the S19 tests. Returns the scripted values, or raises the error named for
the operation (for AC-5). No model is called; the real LLM adapter waits for R-010 (D-058)."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from transcribe_engine.domain.chapters import Chapter, TimedEntity

from transcribe_engine.domain.errors import DomainError


@dataclass
class FakeEnricher:
    chapters_out: Sequence[Chapter] = ()
    summary_out: str = "ملخص"
    entities_out: Sequence[TimedEntity] = ()
    fail: dict[str, DomainError] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    async def chapters(self, text: str) -> Sequence[Chapter]:
        self.calls.append("chapters")
        if "chapters" in self.fail:
            raise self.fail["chapters"]
        return self.chapters_out

    async def summary(self, text: str, max_words: int) -> str:
        self.calls.append("summary")
        if "summary" in self.fail:
            raise self.fail["summary"]
        return self.summary_out

    async def entities(self, text: str) -> Sequence[TimedEntity]:
        self.calls.append("entities")
        if "entities" in self.fail:
            raise self.fail["entities"]
        return self.entities_out
