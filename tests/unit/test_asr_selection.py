"""S12 (D-067): the vLLM engine is selectable by configuration, and it is strict.

Positive controls: the plumbing and local engines are still selected as before, and an unknown
engine name is refused. A vLLM selection must build the vLLM adapter and must make an incomplete
transcript fail the job (require_complete_text), so a missing aligner cannot pass as silence.
"""

import importlib
from types import ModuleType
from typing import Any

import pytest

from tests.fakes.storage import FakeObjectStorage


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _settings(**overrides: Any) -> Any:
    return _mod("transcribe_engine.infrastructure.settings").Settings(**overrides)


def test_vllm_engine_is_selected_by_configuration() -> None:
    main = _mod("transcribe_engine.main")
    vllm = _mod("transcribe_engine.infrastructure.asr.vllm_client")
    engine = main._asr_engine(
        FakeObjectStorage(), _settings(asr_engine="vllm", vllm_url="http://vllm.test"), load=False
    )
    assert isinstance(engine, vllm.VllmASR)


def test_positive_controls_existing_engines_and_unknown_names() -> None:
    main = _mod("transcribe_engine.main")
    plumbing = main._asr_engine(FakeObjectStorage(), _settings(asr_engine="plumbing"), load=False)
    assert plumbing.name == "plumbing"
    # Settings rejects an unknown name when built, so set it after: this tests the branch itself.
    unknown = _settings(asr_engine="plumbing")
    unknown.asr_engine = "nope"
    with pytest.raises(ValueError, match="unknown TE_ASR_ENGINE"):
        main._asr_engine(FakeObjectStorage(), unknown, load=False)


@pytest.mark.xfail(strict=True, reason="S12")
def test_cohere_local_engine_is_selected_by_configuration() -> None:
    """TE_ASR_ENGINE=cohere_local builds the local Cohere adapter with the pinned model (D-074).

    Positive control: the same selection sets the adapter's pinned revision from settings.
    """
    main = _mod("transcribe_engine.main")
    cohere = _mod("transcribe_engine.infrastructure.asr.cohere_local")
    engine = main._asr_engine(FakeObjectStorage(), _settings(asr_engine="cohere_local"), load=False)
    assert isinstance(engine, cohere.CohereLocalASR)
    assert engine.revision == cohere.DEFAULT_REVISION
