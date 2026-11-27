"""Local Cohere Transcribe Arabic ASR (S12, D-074).

The pinned model runs through transformers, on this machine.

- The model is read from the local Hugging Face cache, offline (`local_files_only`), at a pinned
  commit. It runs the repo's own code (`trust_remote_code`), which is why the revision is pinned.
- The model outputs text only, with no word times. The aligner (D-070) places the text on the
  audio. Without an aligner the adapter refuses; it never returns silence for text it cannot place.
- Device: CUDA in float16 when torch sees a GPU, otherwise CPU in float32.
- Errors: out of memory is TransientError (a retry can succeed); other model failures are
  PermanentError. Nothing from the audio or the transcript is put in an error message or a log.
"""

import asyncio
from collections.abc import Callable
from typing import Any

import numpy as np

from transcribe_engine.application.ports.aligner import Aligner
from transcribe_engine.application.ports.asr import ASRCapabilities
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.domain.merge import RawWord
from transcribe_engine.infrastructure.asr.window import read_window_pcm

__all__ = ["DEFAULT_MODEL_ID", "DEFAULT_REVISION", "CohereLocalASR"]

DEFAULT_MODEL_ID = "CohereLabs/cohere-transcribe-arabic-07-2026"
DEFAULT_REVISION = "c3e911b42149bf7a1e53d5cef9878aee87515a23"  # the reviewed commit (D-069)
_PCM_SCALE = 32768.0
_MAX_NEW_TOKENS = 200  # a 30 s chunk is well below this

Runner = Callable[[np.ndarray], str]


class CohereLocalASR:
    name = "cohere-local"
    capabilities = ASRCapabilities(
        native_word_timestamps=False,
        native_segment_timestamps=False,
        max_chunk_seconds=30.0,
        supports_language_hint=True,
        supports_batching=False,
    )

    def __init__(
        self,
        storage: ObjectStorage,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        revision: str = DEFAULT_REVISION,
        device: str | None = None,
        runner: Runner | None = None,
        aligner: Aligner | None = None,
    ) -> None:
        self._storage = storage
        self._model_id = model_id
        self._revision = revision
        self._device = device
        self._runner = runner
        self._aligner = aligner
        self._load_error: PermanentError | None = None
        self._load_lock = asyncio.Lock()
        self.revision = revision

    def load(self) -> None:
        """Load the model now, so a missing or broken cache stops the worker at startup (D-063)."""
        if self._runner is None:
            self._runner = _load_runner(self._model_id, self._device, self._revision)

    async def transcribe(
        self, audio_key: str, chunk: Chunk, *, language: str
    ) -> tuple[RawWord, ...]:
        start = max(0, chunk.start_sample - chunk.pad_before)
        end = chunk.end_sample + chunk.pad_after
        pcm = await read_window_pcm(self._storage, audio_key, start, end)
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / _PCM_SCALE
        if samples.size == 0:
            return ()
        runner = await self._ensure_runner()
        text = await asyncio.to_thread(_run, runner, samples)
        if not text:
            return ()
        if self._aligner is None:
            raise PermanentError(
                "cohere returned text without word times; a forced aligner is required"
            )
        return await self._aligner.align(audio_key, chunk, text, language=language)

    async def _ensure_runner(self) -> Runner:
        async with self._load_lock:
            if self._runner is None:
                if self._load_error is not None:
                    raise self._load_error
                try:
                    self._runner = await asyncio.to_thread(
                        _load_runner, self._model_id, self._device, self._revision
                    )
                except PermanentError as exc:
                    self._load_error = exc
                    raise
            return self._runner


def _run(runner: Runner, samples: np.ndarray) -> str:
    try:
        return runner(samples).strip()
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            raise TransientError("model ran out of memory on this chunk") from exc
        raise PermanentError("model failed on this chunk") from exc
    except ValueError as exc:
        raise PermanentError("model rejected this chunk") from exc


def _load_runner(model_id: str, device: str | None, revision: str) -> Runner:
    """Load the processor and model offline at the pinned revision; return a text runner."""
    if device not in (None, "cuda", "cpu"):
        raise PermanentError("device must be cuda, cpu or unset")
    import torch  # noqa: PLC0415 - lazy: torch is an optional extra, absent in CI (D-063)
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor  # noqa: PLC0415 - lazy, as above

    # transformers is untyped for these classes; the calls below are checked by the tests, not mypy.
    processor_cls: Any = AutoProcessor
    model_cls: Any = AutoModelForSpeechSeq2Seq

    use_cuda = device == "cuda" or (device is None and torch.cuda.is_available())
    target = "cuda" if use_cuda else "cpu"
    dtype = torch.float16 if use_cuda else torch.float32
    kwargs: dict[str, Any] = {
        "revision": revision,
        "trust_remote_code": True,
        "local_files_only": True,
    }
    try:
        processor = processor_cls.from_pretrained(model_id, **kwargs)
        model = model_cls.from_pretrained(model_id, dtype=dtype, **kwargs)
    except OSError as exc:
        raise PermanentError(f"model {model_id} is not in the local cache") from exc
    model = model.to(target).eval()

    def run(samples: np.ndarray) -> str:
        inputs = processor(audio=samples, sampling_rate=16000, return_tensors="pt", language="ar")
        inputs.to(model.device, dtype=model.dtype)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=_MAX_NEW_TOKENS)
        return str(processor.decode(out, skip_special_tokens=True, language="ar")[0])

    return run
