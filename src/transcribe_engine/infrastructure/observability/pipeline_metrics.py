"""Prometheus adapter of the pipeline metrics port (S20). The counters live in metrics.py; this
module only maps the port's three calls onto them."""

from transcribe_engine.infrastructure.observability.metrics import (
    CACHE_HITS,
    CACHE_LOOKUPS,
    SEGMENTS,
    STAGE_RTF,
)

__all__ = ["PrometheusPipelineMetrics"]


class PrometheusPipelineMetrics:
    def count_segments(self, count: int) -> None:
        if count > 0:
            SEGMENTS.inc(count)

    def count_cache_lookup(self, hit: bool) -> None:
        CACHE_LOOKUPS.inc()
        if hit:
            CACHE_HITS.inc()

    def observe_rtf(self, stage: str, value: float) -> None:
        STAGE_RTF.labels(stage=stage).observe(value)
