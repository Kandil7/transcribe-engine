"""S20 (design: monitoring): the result cache's lookups and hits are counted
(transcribe_cache_lookups and transcribe_cache_hits), so the hit ratio can be computed.

Positive control: a stored result counts one lookup and one hit. Negative control: a file with no
stored result counts one lookup and no hit, so a counter that always says "hit" cannot pass.
"""

import hashlib
import importlib
from types import ModuleType
from typing import Any

import pytest

from tests.unit.application.test_ingest_job import _config, _ingest, _job, _world


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


@pytest.mark.xfail(strict=True, reason="S20")
async def test_a_stored_result_counts_one_lookup_and_one_hit(tmp_path: Any) -> None:
    jobs = _mod("transcribe_engine.domain.jobs")
    keys = _mod("transcribe_engine.domain.keys")
    fake_metrics = _mod("tests.fakes.metrics").FakeMetrics()
    upload = b"RIFF-cached-bytes"
    store, _inner, storage, probe, normalizer, make_uow = await _world(upload)
    key = keys.result_key(hashlib.sha256(upload).hexdigest(), _config())
    store.results_by_key[key] = jobs.Result(
        id=key, result_key=key, media_id="old-media", config=_config(), ref_count=1
    )

    await _ingest(storage, probe, normalizer, make_uow, tmp_path, metrics=fake_metrics)(_job())

    assert (fake_metrics.cache_lookups, fake_metrics.cache_hits) == (1, 1)


@pytest.mark.xfail(strict=True, reason="S20")
async def test_a_new_file_counts_one_lookup_and_no_hit(tmp_path: Any) -> None:
    fake_metrics = _mod("tests.fakes.metrics").FakeMetrics()
    _store, _inner, storage, probe, normalizer, make_uow = await _world(b"RIFF-new-bytes")

    await _ingest(storage, probe, normalizer, make_uow, tmp_path, metrics=fake_metrics)(_job())

    assert (fake_metrics.cache_lookups, fake_metrics.cache_hits) == (1, 0)
