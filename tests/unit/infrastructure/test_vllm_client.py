"""S12 AC-3: the vLLM client maps HTTP and transport failures to the domain error classes.
The third-party boundary (httpx) is mocked with a MockTransport; no server is needed.

Positive control: a 200 response with a valid body is returned, so a client that raises on
everything cannot pass.
"""

import importlib
from collections.abc import Callable
from types import ModuleType

import httpx
import pytest

from transcribe_engine.domain.errors import PermanentError, TransientError


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> object:
    vllm_client = _mod("transcribe_engine.infrastructure.asr.vllm_client")
    return vllm_client.VllmClient(
        "http://vllm.test",
        "model-x",
        transport=httpx.MockTransport(handler),
    )


async def _call(client: object) -> object:
    return await client.transcribe(b"RIFF", language="ar", temperature=0.0)  # type: ignore[attr-defined]


async def test_error_mapping() -> None:
    ok = _client(lambda _r: httpx.Response(200, json={"text": "", "words": []}))
    assert await _call(ok) is not None

    unavailable = _client(lambda _r: httpx.Response(503))
    with pytest.raises(TransientError):
        await _call(unavailable)

    bad_request = _client(lambda _r: httpx.Response(400, json={"error": "bad audio"}))
    with pytest.raises(PermanentError):
        await _call(bad_request)

    def slow(_r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(TransientError):
        await _call(_client(slow))
