"""Contract of the PipelineMetrics port (S20): one suite, run against the fake and the Prometheus
adapter. Each check has a positive control (the counter moved by the reported amount), so an adapter
that drops the calls cannot pass.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from prometheus_client import REGISTRY

from tests.fakes.metrics import FakeMetrics
from transcribe_engine.infrastructure.observability.pipeline_metrics import (
    PrometheusPipelineMetrics,
)

pytestmark = [pytest.mark.contract]


@dataclass
class Reading:
    segments: float
    lookups: float
    hits: float
    rtf_count: float


def _prom_reading() -> Reading:
    def value(name: str, labels: dict[str, str] | None = None) -> float:
        return REGISTRY.get_sample_value(name, labels or {}) or 0.0

    return Reading(
        segments=value("transcribe_segments_total"),
        lookups=value("transcribe_cache_lookups_total"),
        hits=value("transcribe_cache_hits_total"),
        rtf_count=value("transcribe_stage_rtf_count", {"stage": "asr"}),
    )


def _fake_reading(fake: FakeMetrics) -> Reading:
    return Reading(
        segments=fake.segments,
        lookups=fake.cache_lookups,
        hits=fake.cache_hits,
        rtf_count=sum(1 for stage, _ in fake.rtf if stage == "asr"),
    )


@pytest.fixture(params=["fake", "prometheus"])
def recorder(request: pytest.FixtureRequest) -> tuple[Any, Any]:
    if request.param == "fake":
        fake = FakeMetrics()
        return fake, lambda: _fake_reading(fake)
    return PrometheusPipelineMetrics(), _prom_reading


def _delta(before: Reading, after: Reading) -> Reading:
    return Reading(
        segments=after.segments - before.segments,
        lookups=after.lookups - before.lookups,
        hits=after.hits - before.hits,
        rtf_count=after.rtf_count - before.rtf_count,
    )


def test_each_report_moves_its_own_counter(recorder: tuple[Any, Any]) -> None:
    """Positive control: 3 segments, one lookup that hits, one lookup that misses, and one ASR
    stage time move exactly those counters by exactly those amounts."""
    metrics, read = recorder
    before = read()
    metrics.count_segments(3)
    metrics.count_cache_lookup(hit=True)
    metrics.count_cache_lookup(hit=False)
    metrics.observe_rtf("asr", 0.4)
    delta = _delta(before, read())
    assert (delta.segments, delta.lookups, delta.hits, delta.rtf_count) == (3, 2, 1, 1)


def test_a_zero_segment_report_moves_nothing(recorder: tuple[Any, Any]) -> None:
    """Negative control: an empty transcript reports zero segments and nothing changes."""
    metrics, read = recorder
    before = read()
    metrics.count_segments(0)
    assert _delta(before, read()).segments == 0
