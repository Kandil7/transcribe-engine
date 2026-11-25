"""Acceptance tests for S03 — PipelineConfig and canonical JSON (S03 spec)."""

import hashlib
import importlib
import math
from types import ModuleType

import pytest
from hypothesis import given
from hypothesis import strategies as st


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.config")


def _config(**overrides: object) -> object:
    t = _mod()
    fields: dict[str, object] = {
        "engine": "faster-whisper",
        "model_revision": "large-v3@r1",
        "language": "ar",
        "decoding_params": {"beam_size": 5, "temperature": 0},
        "vad_params": {"threshold": 0.5},
        "diarization_enabled": False,
        "pipeline_version": "1.0.0",
    }
    fields.update(overrides)
    return t.PipelineConfig(**fields)  # type: ignore[arg-type]


def test_config_hash_is_sha256_of_canonical_json() -> None:
    cfg = _config()
    expected = hashlib.sha256(cfg.canonical_json().encode("utf-8")).hexdigest()  # type: ignore[attr-defined]
    assert cfg.config_hash() == expected  # type: ignore[attr-defined]


@given(
    mapping=st.dictionaries(
        st.text(min_size=1, max_size=8), st.integers(min_value=-5, max_value=5), max_size=8
    )
)
def test_canonical_json_is_order_independent(mapping: dict[str, int]) -> None:
    """AC-2: permuted insertion order gives identical canonical JSON."""
    forward = _config(decoding_params=dict(mapping))
    reversed_map = dict(reversed(list(mapping.items())))
    backward = _config(decoding_params=reversed_map)
    assert forward.canonical_json() == backward.canonical_json()  # type: ignore[attr-defined]


def test_canonical_json_format() -> None:
    cfg = _config()
    text = cfg.canonical_json()  # type: ignore[attr-defined]
    assert " " not in text
    assert text.startswith('{"decoding_params":')
    assert text.index('"diarization_enabled"') < text.index('"engine"')


def test_rejects_nan_and_nested() -> None:
    """AC-6: NaN, Infinity and nested decoding_params are rejected with ValueError."""
    with pytest.raises(ValueError, match="finite"):
        _config(decoding_params={"temperature": math.nan})
    with pytest.raises(ValueError, match="finite"):
        _config(decoding_params={"temperature": math.inf})
    with pytest.raises(ValueError, match="flat"):
        _config(decoding_params={"nested": {"a": 1}})
    with pytest.raises(ValueError, match="flat"):
        _config(vad_params={"nested": [1, 2]})


@pytest.mark.parametrize("language", ["", "auto"])
def test_language_must_be_explicit(language: str) -> None:
    with pytest.raises(ValueError, match="explicit language"):
        _config(language=language)


def test_int_and_float_zero_produce_different_hashes() -> None:
    """Documented edge case: 0.0 and 0 are different JSON values (adapters emit stable types)."""
    a = _config(decoding_params={"temperature": 0})
    b = _config(decoding_params={"temperature": 0.0})
    assert a.config_hash() != b.config_hash()  # type: ignore[attr-defined]
