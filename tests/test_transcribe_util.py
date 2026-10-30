"""Offline tests for src/transcribe.py utilities — cache resolver + dispatch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transcribe import resolve_cache_dir


def _mk(root: Path, model_id: str) -> None:
    (root / ("models--" + model_id.replace("/", "--"))).mkdir(parents=True)


def test_resolver_prefers_unique_holder(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    hub = tmp_path / "legacy" / "hub"
    _mk(legacy, "org/model-a")
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setenv("HF_HOME", str(legacy))
    assert resolve_cache_dir("org/model-a") == str(legacy)


def test_resolver_none_when_missing(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    hub = legacy / "hub"
    hub.mkdir(parents=True)
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setenv("HF_HOME", str(legacy))
    assert resolve_cache_dir("org/nowhere") is None


def test_resolver_none_when_ambiguous(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    hub = legacy / "hub"
    _mk(legacy, "org/dup")
    _mk(hub, "org/dup")
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setenv("HF_HOME", str(legacy))
    assert resolve_cache_dir("org/dup") is None  # both hold it: hub default


def test_stub_dir_does_not_hide_real_holder(tmp_path, monkeypatch):
    # a failed download leaves a stub with tiny config files but no weights;
    # the root with the actual content must win
    legacy = tmp_path / "legacy"
    hub = legacy / "hub"
    _mk(legacy, "org/model-b")
    _mk(hub, "org/model-b")
    (legacy / "models--org--model-b" / "weights.bin").write_bytes(b"x" * 1024)
    (hub / "models--org--model-b" / "config.json").write_bytes(b"{}")
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setenv("HF_HOME", str(legacy))
    assert resolve_cache_dir("org/model-b") == str(legacy)


def test_resolver_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    assert resolve_cache_dir("org/model") is None


def test_nemotron_dispatch(monkeypatch):
    import diarize

    calls = {}

    def fake_nemotron(audio_path, device="cuda", hf_token=None, model_id=""):
        calls["backend"] = "nemotron"
        calls["model_id"] = model_id
        return [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}]

    def fake_pyannote(
        audio_path, device="cuda", hf_token=None, model_id="", num_speakers=None
    ):
        calls["backend"] = "pyannote"
        return []

    monkeypatch.setattr(diarize, "diarize_nemotron", fake_nemotron)
    monkeypatch.setattr(diarize, "diarize_pyannote", fake_pyannote)

    turns = diarize.diarize_audio("x.wav", model_id="nvidia/Nemotron-3-Diarization")
    assert calls["backend"] == "nemotron" and turns[0]["speaker"] == "SPEAKER_00"

    diarize.diarize_audio("x.wav", model_id="pyannote/speaker-diarization-community-1")
    assert calls["backend"] == "pyannote"


def test_lid_retry_after_freeing_models(monkeypatch):
    import lid
    import transcribe

    calls = []

    def fake_lid(audio_path, device="cuda", model_id=""):
        calls.append(device)
        if len(calls) == 1:
            raise OSError(
                "The paging file is too small for this operation to complete. (os error 1455)"
            )
        return {"lang": "ara", "confidence": 0.99, "top": [("ara", 0.99)]}

    monkeypatch.setattr(lid, "lid_audio", fake_lid)
    session = transcribe.TranscribeSession(transcribe.TranscribeConfig(device="cuda"))
    result = {}
    session._apply_lid(result, "x.wav")
    assert calls == ["cuda", "cuda"]  # freed models, retried same device
    assert session.asr is None  # ASR dropped to reclaim commit
    assert result["lid_lang"] == "ara"
    assert result["lid_status"] == "ok"


def test_lid_cpu_last_resort(monkeypatch):
    import lid
    import transcribe

    calls = []

    def fake_lid(audio_path, device="cuda", model_id=""):
        calls.append(device)
        if device != "cpu":
            raise OSError("paging file too small (os error 1455)")
        return {"lang": "ara", "confidence": 0.99, "top": [("ara", 0.99)]}

    monkeypatch.setattr(lid, "lid_audio", fake_lid)
    session = transcribe.TranscribeSession(transcribe.TranscribeConfig(device="cuda"))
    result = {}
    session._apply_lid(result, "x.wav")
    assert calls == ["cuda", "cuda", "cpu"]  # free -> retry -> cpu last resort
    assert result["lid_status"] == "ok"


def test_lid_non_memory_error_fails_without_fallback(monkeypatch):
    import lid
    import transcribe

    calls = []

    def fake_lid(audio_path, device="cuda", model_id=""):
        calls.append(device)
        raise ValueError("bad audio")

    monkeypatch.setattr(lid, "lid_audio", fake_lid)
    session = transcribe.TranscribeSession(transcribe.TranscribeConfig(device="cuda"))
    result = {}
    session._apply_lid(result, "x.wav")
    assert calls == ["cuda"]  # no retry for non-memory errors
    assert result["lid_status"] == "failed"
    assert result["lid_lang"] == ""


def test_local_only_env_restored(monkeypatch):
    import os

    import transcribe

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    with transcribe.local_only():
        assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert "HF_HUB_OFFLINE" not in os.environ

    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    with transcribe.local_only():
        assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["HF_HUB_OFFLINE"] == "0"  # prior value restored


def test_load_local_first_prefers_cache(monkeypatch):
    import os

    import transcribe

    seen = []

    def loader(x):
        seen.append(os.environ.get("HF_HUB_OFFLINE"))
        return x * 2

    assert transcribe.load_local_first(loader, 21) == 42
    assert seen == ["1"]  # cache-only attempt, no fallback needed


def test_load_local_first_falls_back_online(monkeypatch):
    import os

    import transcribe

    seen = []

    def flaky(x):
        seen.append(os.environ.get("HF_HUB_OFFLINE"))
        if os.environ.get("HF_HUB_OFFLINE") == "1":
            raise OSError("not in cache")
        return x * 2

    assert transcribe.load_local_first(flaky, 21) == 42
    assert seen == ["1", None]  # cache miss -> online retry


def test_load_local_first_propagates_final_error():
    import transcribe

    def broken():
        raise ValueError("always fails")

    try:
        transcribe.load_local_first(broken)
    except ValueError as e:
        assert "always fails" in str(e)
    else:
        raise AssertionError("second failure must propagate")
