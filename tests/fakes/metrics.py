"""In-memory pipeline metrics for the S20 tests. It records what the use cases report through the
metrics port, so a test can read the counts back."""

from dataclasses import dataclass, field


@dataclass
class FakeMetrics:
    segments: int = 0
    cache_lookups: int = 0
    cache_hits: int = 0
    rtf: list[tuple[str, float]] = field(default_factory=list)

    def count_segments(self, count: int) -> None:
        self.segments += count

    def count_cache_lookup(self, hit: bool) -> None:
        self.cache_lookups += 1
        self.cache_hits += int(hit)

    def observe_rtf(self, stage: str, value: float) -> None:
        self.rtf.append((stage, value))
