"""Offline tests for src/prefetch.py — orchestration with mocked loaders."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import prefetch


def test_prefetch_one_all_local(monkeypatch):
    for name in prefetch.PREFETCH_MODELS:
        monkeypatch.setitem(prefetch._LOADERS, name, lambda device: object())
    for name in prefetch.PREFETCH_MODELS:
        assert prefetch._prefetch_one(name, "cpu") == "local"


def test_prefetch_one_downloaded_on_cache_miss(monkeypatch):
    def miss_then_fetch(device):
        if os.environ.get("HF_HUB_OFFLINE") == "1":
            raise OSError("not cached")
        return object()

    monkeypatch.setitem(prefetch._LOADERS, "asr", miss_then_fetch)
    assert prefetch._prefetch_one("asr", "cpu") == "downloaded"


def test_prefetch_one_propagates_hard_failure(monkeypatch):
    def broken(device):
        raise RuntimeError("model repo gone")

    monkeypatch.setitem(prefetch._LOADERS, "asr", broken)
    try:
        prefetch._prefetch_one("asr", "cpu")
    except RuntimeError as e:
        assert "model repo gone" in str(e)
    else:
        raise AssertionError("hard failure must propagate")


def test_prefetch_models_isolates_processes(monkeypatch):
    spawned = []

    def fake_worker(name, device):
        spawned.append((name, device))
        return "local" if name != "lid" else "downloaded"

    monkeypatch.setattr(prefetch, "_run_worker", fake_worker)
    results = prefetch.prefetch_models("cpu")
    assert results == {
        "asr": "local",
        "aligner": "local",
        "nemotron": "local",
        "lid": "downloaded",
        "dialect": "local",
    }
    assert [n for n, _ in spawned] == list(prefetch.PREFETCH_MODELS)


def test_run_worker_parses_result_line(monkeypatch):
    import subprocess as sp

    class FakeProc:
        returncode = 0
        stdout = "noise\nRESULT asr local\n"
        stderr = ""

    monkeypatch.setattr(sp, "run", lambda *a, **k: FakeProc())
    assert prefetch._run_worker("asr", "cpu") == "local"


def test_run_worker_raises_on_worker_failure(monkeypatch):
    import subprocess as sp

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "boom: model load exploded"

    monkeypatch.setattr(sp, "run", lambda *a, **k: FakeProc())
    try:
        prefetch._run_worker("asr", "cpu")
    except RuntimeError as e:
        assert "model load exploded" in str(e)
    else:
        raise AssertionError("worker failure must raise")
