"""S12 ASR contract (AC-1): every engine declares its name, revision and capabilities. Run against
the fake, the plumbing engine and the vLLM adapter (HTTP mocked). Needs no GPU.

Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
from types import ModuleType

import httpx
import pytest

pytestmark = pytest.mark.contract


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _engines() -> list[object]:
    fake_asr = _mod("tests.fakes.asr").FakeASR()
    plumbing = _mod("transcribe_engine.infrastructure.asr.plumbing").PlumbingASR()
    vllm_asr = _mod("transcribe_engine.infrastructure.asr.vllm_client").VllmASR(
        storage=_mod("tests.fakes.storage").FakeObjectStorage(),
        client=_mod("transcribe_engine.infrastructure.asr.vllm_client").VllmClient(
            "http://vllm.test",
            "model-x",
            transport=httpx.MockTransport(lambda _r: httpx.Response(200)),
        ),
    )
    return [fake_asr, plumbing, vllm_asr]


@pytest.mark.xfail(strict=True, reason="S12")
def test_capabilities_declared() -> None:
    capabilities_type = _mod("transcribe_engine.application.ports.asr").ASRCapabilities
    for engine in _engines():
        assert isinstance(engine.name, str)  # type: ignore[attr-defined]
        assert engine.name  # type: ignore[attr-defined]
        assert engine.revision  # type: ignore[attr-defined]
        capabilities = engine.capabilities  # type: ignore[attr-defined]
        assert isinstance(capabilities, capabilities_type)
        assert capabilities.max_chunk_seconds > 0
