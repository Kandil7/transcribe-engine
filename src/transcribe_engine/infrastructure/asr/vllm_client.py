"""vLLM ASR adapter (S12, ADR-0005): the model runs in its own vLLM service in BF16; the worker
calls it over HTTP with the OpenAI-compatible transcription route.

- Errors: transport failures, timeouts, 429 and 5xx are TransientError; other 4xx and malformed
  bodies are PermanentError (AC-3). Nothing from the response is logged.
- The chunk's padded window is read from storage with a Range GET and wrapped as a WAV, so no
  per-chunk file is written (S10).
- Times leave the API in seconds and are converted to integer samples at this boundary, once.
"""

import io
import wave
from typing import Any

import httpx

from transcribe_engine.application.ports.aligner import Aligner
from transcribe_engine.application.ports.asr import ASRCapabilities
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.chunks import NORMALIZED_SAMPLE_RATE, Chunk
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.domain.merge import RawWord
from transcribe_engine.infrastructure.asr.window import BYTES_PER_SAMPLE, read_window_pcm

__all__ = ["VllmASR", "VllmClient"]

_ROUTE = "/v1/audio/transcriptions"


class VllmClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self._model = model
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=timeout_s)

    async def transcribe(self, wav: bytes, *, language: str, temperature: float) -> dict[str, Any]:
        data = {
            "model": self._model,
            "language": language,
            "temperature": str(temperature),
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        files = {"file": ("chunk.wav", wav, "audio/wav")}
        try:
            response = await self._http.post(_ROUTE, data=data, files=files)
        except httpx.TransportError as exc:  # includes timeouts
            raise TransientError("vLLM unreachable or timed out") from exc
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS or response.status_code >= 500:
            raise TransientError(f"vLLM answered {response.status_code}")
        if response.status_code >= 400:
            raise PermanentError(f"vLLM refused the request ({response.status_code})")
        try:
            body = response.json()
        except ValueError as exc:
            raise PermanentError("vLLM returned a body that is not JSON") from exc
        if not isinstance(body, dict):
            raise PermanentError("vLLM returned a JSON value that is not an object")
        return body

    async def aclose(self) -> None:
        await self._http.aclose()


class VllmASR:
    """ASREngine over VllmClient. `name` and `revision` are provenance (design: الـ Ports)."""

    capabilities = ASRCapabilities(
        native_word_timestamps=True,
        native_segment_timestamps=True,
        max_chunk_seconds=30.0,
        supports_language_hint=True,
        supports_batching=True,
    )

    def __init__(
        self,
        storage: ObjectStorage,
        client: VllmClient,
        *,
        name: str = "vllm",
        revision: str = "pending-s00",
        aligner: Aligner | None = None,
    ) -> None:
        self._storage = storage
        self._client = client
        self._aligner = aligner  # places text that has no word times (S14, D-070)
        self.name = name
        self.revision = revision

    async def transcribe(
        self, audio_key: str, chunk: Chunk, *, language: str
    ) -> tuple[RawWord, ...]:
        start = max(0, chunk.start_sample - chunk.pad_before)
        end = chunk.end_sample + chunk.pad_after
        wav = await self._window_as_wav(audio_key, start, end)
        body = await self._client.transcribe(wav, language=language, temperature=0.0)
        words = _words(body, chunk.sample_rate)
        text = str(body.get("text", "")).strip()
        if words or not text:
            return words
        if self._aligner is None:
            # Text with no word times cannot be placed in the file: refuse it, never return
            # silence (D-067).
            raise PermanentError(
                "vLLM returned text without word times; a forced aligner is required"
            )
        return await self._aligner.align(audio_key, chunk, text, language=language)

    async def _window_as_wav(self, audio_key: str, start: int, end: int) -> bytes:
        pcm = await read_window_pcm(self._storage, audio_key, start, end)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(BYTES_PER_SAMPLE)
            out.setframerate(NORMALIZED_SAMPLE_RATE)
            out.writeframes(pcm)
        return buffer.getvalue()


def _words(body: dict[str, Any], sample_rate: int) -> tuple[RawWord, ...]:
    raw_words = body.get("words", [])
    if not isinstance(raw_words, list):
        raise PermanentError("vLLM returned words that are not a list")
    words: list[RawWord] = []
    for item in raw_words:
        try:
            text = str(item["word"])
            start_s = float(item["start"])
            end_s = float(item["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PermanentError("vLLM returned a malformed word") from exc
        words.append(
            RawWord(
                text=text,
                local_start=round(start_s * sample_rate),
                local_end=round(end_s * sample_rate),
                conf=None,
            )
        )
    return tuple(words)
