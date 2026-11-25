"""Acceptance tests for S03 — deterministic keys (specs/S03-pipeline-config-and-keys.md, D-007)."""

import dataclasses
import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(f"transcribe_engine.domain.{name}")


def _config() -> object:
    cfg = _mod("config")
    return cfg.PipelineConfig(
        engine="faster-whisper",
        model_revision="large-v3@r1",
        language="ar",
        decoding_params={"beam_size": 5, "temperature": 0},
        vad_params={"threshold": 0.5},
        diarization_enabled=False,
        pipeline_version="1.0.0",
    )


FILE_SHA = "f" * 64

# Changed values for each PipelineConfig field; each must change result_key on its own.
CHANGES = {
    "engine": "whisper-cpp",
    "model_revision": "large-v3@r2",
    "language": "ar-EG",
    "decoding_params": {"beam_size": 1, "temperature": 0},
    "vad_params": {"threshold": 0.6},
    "diarization_enabled": True,
    "pipeline_version": "1.0.1",
}


@pytest.mark.xfail(strict=True, reason="S03")
@pytest.mark.parametrize("field", sorted(CHANGES))
def test_each_config_field_changes_key(field: str) -> None:
    """AC-1: changing any single config field changes result_key."""
    keys = _mod("keys")
    base = _config()
    changed = dataclasses.replace(base, **{field: CHANGES[field]})  # type: ignore[type-var]
    assert keys.result_key(FILE_SHA, base) != keys.result_key(FILE_SHA, changed)  # type: ignore[arg-type]


@pytest.mark.xfail(strict=True, reason="S03")
def test_result_key_depends_on_file_hash() -> None:
    keys = _mod("keys")
    assert keys.result_key(FILE_SHA, _config()) != keys.result_key("e" * 64, _config())  # type: ignore[arg-type]


@pytest.mark.xfail(strict=True, reason="S03")
def test_isolation_scope_changes_key() -> None:
    """AC-3: an isolation scope changes the key; different scopes differ; no scope is stable."""
    keys = _mod("keys")
    cfg = _config()
    shared = keys.result_key(FILE_SHA, cfg)  # type: ignore[arg-type]
    tenant_a = keys.result_key(FILE_SHA, cfg, "tenant-a")  # type: ignore[arg-type]
    tenant_b = keys.result_key(FILE_SHA, cfg, "tenant-b")  # type: ignore[arg-type]
    assert shared != tenant_a != tenant_b
    assert shared == keys.result_key(FILE_SHA, cfg, None)  # type: ignore[arg-type]


@pytest.mark.xfail(strict=True, reason="S03")
def test_result_key_golden() -> None:
    keys = _mod("keys")
    assert keys.result_key(FILE_SHA, _config()) == (  # type: ignore[arg-type]
        "res_51c9ade9b0a96afc6e0965e16f0137e976befa4cd58fe268ae8d51dd629de43f"
    )


@pytest.mark.xfail(strict=True, reason="S03")
def test_chunk_id_stable_across_runs() -> None:
    """AC-4: golden values; the same inputs always give the same id."""
    keys = _mod("keys")
    got = keys.chunk_id("a" * 64, "b" * 64, 3, 16_000, 32_000)
    assert got == "chk_b11628b04688fea4df545d9ffe7716d3764a39b0dfe527c50226f4c70870b222"
    assert got == keys.chunk_id("a" * 64, "b" * 64, 3, 16_000, 32_000)


@pytest.mark.xfail(strict=True, reason="S03")
def test_rag_chunk_id_golden() -> None:
    keys = _mod("keys")
    assert keys.rag_chunk_id("tr_1", 2, 1000, 4500) == (
        "rag_8d60bb336145cd3ef79247cfe3dfd3de9e69d39229bf039a77ee5931487d1906"
    )


@pytest.mark.xfail(strict=True, reason="S03")
def test_rag_chunk_id_rejects_pipe_in_transcript_id() -> None:
    keys = _mod("keys")
    with pytest.raises(ValueError, match="must not contain"):
        keys.rag_chunk_id("tr|1", 1, 0, 1)


@pytest.mark.xfail(strict=True, reason="S03")
def test_embedding_id_golden_and_unambiguous() -> None:
    keys = _mod("keys")
    got = keys.embedding_id("مرحبا بالعالم", "bge-m3")
    assert got == "emb_d624750b110e787229f076ca9b837563bf25789734608fb332b1555f9f88a767"
    # Without JSON framing, these two would collide on the joined string "a|b|c".
    assert keys.embedding_id("a|b", "c") != keys.embedding_id("a", "b|c")


@pytest.mark.xfail(strict=True, reason="S03")
def test_all_keys_have_prefix_and_lowercase_hex() -> None:
    keys = _mod("keys")
    values = [
        (keys.result_key(FILE_SHA, _config()), "res_"),  # type: ignore[arg-type]
        (keys.chunk_id("a" * 64, "b" * 64, 0, 0, 1), "chk_"),
        (keys.rag_chunk_id("tr", 1, 0, 1), "rag_"),
        (keys.embedding_id("x", "m"), "emb_"),
    ]
    for value, prefix in values:
        assert value.startswith(prefix)
        body = value[len(prefix) :]
        assert len(body) == 64
        assert body == body.lower()
        int(body, 16)
