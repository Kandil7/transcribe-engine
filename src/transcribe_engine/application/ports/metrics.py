"""Pipeline metrics port (S20, design: monitoring).

The use cases report what they did; the Prometheus adapter in infrastructure turns it into the
design's metrics. A use case never imports prometheus.
"""

from typing import Protocol

__all__ = ["PipelineMetrics"]


class PipelineMetrics(Protocol):
    def count_segments(self, count: int) -> None: ...

    def count_cache_lookup(self, hit: bool) -> None: ...

    def observe_rtf(self, stage: str, value: float) -> None:
        """Processing time over audio duration for one stage (1.0 means real time)."""
        ...
