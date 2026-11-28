"""D-083 (S17): the optional speaker count is part of the pipeline configuration. It is left
out of the configuration hash when unset, so existing jobs keep their hash.

Positive control: a set count changes the hash. Negative control: a count outside
1 to 10 is refused.
"""

import importlib
from types import ModuleType

import pytest


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.config")


def _config(**extra: object) -> object:
    return _mod().PipelineConfig(
        engine="whisper-local",
        model_revision="rev",
        language="ar",
        decoding_params={},
        vad_params={},
        diarization_enabled=True,
        pipeline_version="1.0.0",
        **extra,
    )


@pytest.mark.xfail(strict=True, reason="S17")
def test_unset_speakers_keep_the_hash_and_set_speakers_change_it() -> None:
    unset = _config()
    assert "speakers" not in unset.canonical_json()
    assert _config(speakers=None).config_hash() == unset.config_hash()
    assert _config(speakers=3).config_hash() != unset.config_hash()


@pytest.mark.xfail(strict=True, reason="S17")
def test_speakers_outside_one_to_ten_are_refused() -> None:
    with pytest.raises(ValueError, match="speakers"):
        _config(speakers=0)
    with pytest.raises(ValueError, match="speakers"):
        _config(speakers=11)
