"""Local Whisper ASR (S12, D-063): openai/whisper-large-v3-turbo through transformers.

The model is read from the local Hugging Face cache.

- Loaded offline (`local_files_only`): a missing model is a PermanentError, never a download.
- Device: CUDA in FP16 when torch sees a GPU, otherwise CPU in FP32 (the cache holds FP16 weights).
- Language: the job's ISO code maps to Whisper's language name (ar -> arabic).
- Word times come from the pipeline's word timestamps, in seconds from the start of the chunk's
  padded window; they become integer samples once, here (CLAUDE.md time units).
- Errors: out of memory is TransientError (a retry can succeed); any other model failure is
  PermanentError. Nothing from the audio or the transcript is put in an error message or a log.
"""

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from transcribe_engine.application.ports.asr import ASRCapabilities
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.chunks import NORMALIZED_SAMPLE_RATE, Chunk
from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.domain.merge import RawWord
from transcribe_engine.infrastructure.asr.window import read_window_pcm

__all__ = ["DEFAULT_MODEL_ID", "WhisperLocalASR", "words_from_output"]

DEFAULT_MODEL_ID = "openai/whisper-large-v3-turbo"
_PCM_SCALE = 32768.0  # 16-bit samples to float in [-1, 1)
_LANGUAGE_NAMES: Mapping[str, str] = {"ar": "arabic"}
_CHUNK_SECONDS = 30  # Whisper's own window; longer inputs are split by the pipeline

Pipeline = Callable[..., Any]


class WhisperLocalASR:
    name = "whisper-local"
    capabilities = ASRCapabilities(
        native_word_timestamps=True,
        native_segment_timestamps=True,
        max_chunk_seconds=float(_CHUNK_SECONDS),
        supports_language_hint=True,
        supports_batching=False,
    )

    def __init__(
        self,
        storage: ObjectStorage,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        device: str | None = None,
        pipeline: Pipeline | None = None,
        revision: str | None = None,
    ) -> None:
        self._storage = storage
        self._model_id = model_id
        self._device = device
        self._pipeline = pipeline
        self._load_lock = asyncio.Lock()
        self._load_error: PermanentError | None = (
            None  # a failed load is remembered, not retried (review)
        )
        self.revision = revision or _cached_revision(model_id)

    async def transcribe(
        self, audio_key: str, chunk: Chunk, *, language: str
    ) -> tuple[RawWord, ...]:
        start = max(0, chunk.start_sample - chunk.pad_before)
        end = chunk.end_sample + chunk.pad_after
        pcm = await read_window_pcm(self._storage, audio_key, start, end)
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / _PCM_SCALE
        if samples.size == 0:
            return ()
        pipeline = await self._ensure_pipeline()
        output = await asyncio.to_thread(
            _run,
            pipeline,
            samples,
            _LANGUAGE_NAMES.get(language, language),
        )
        try:
            return words_from_output(output, chunk.sample_rate)
        except (AttributeError, TypeError, ValueError) as exc:
            raise PermanentError("the model returned an unreadable word") from exc

    def load(self) -> None:
        """Load the model now, so a missing or broken cache stops the worker at startup (D-063)."""
        if self._pipeline is None:
            self._pipeline = _load_pipeline(self._model_id, self._device, self.revision)

    async def _ensure_pipeline(self) -> Pipeline:
        async with self._load_lock:
            if self._pipeline is None:
                if self._load_error is not None:
                    raise self._load_error
                try:
                    self._pipeline = await asyncio.to_thread(
                        _load_pipeline, self._model_id, self._device, self.revision
                    )
                except PermanentError as exc:
                    self._load_error = exc
                    raise
            return self._pipeline


def words_from_output(output: Mapping[str, Any], sample_rate: int) -> tuple[RawWord, ...]:
    """Word times in samples from the pipeline's word chunks.

    Empty words are dropped; a word without
    an end time keeps its start."""
    raw_chunks = output.get("chunks", [])
    if not isinstance(raw_chunks, list):
        raise PermanentError("the model returned word chunks that are not a list")
    words: list[RawWord] = []
    for item in raw_chunks:
        text = str(item.get("text", "")).strip()
        timestamp = item.get("timestamp")
        if not text or not isinstance(timestamp, (list, tuple)) or len(timestamp) != 2:
            continue
        start_s = timestamp[0]
        end_s = timestamp[1] if timestamp[1] is not None else start_s
        if start_s is None:
            continue
        words.append(
            RawWord(
                text=text,
                local_start=round(float(start_s) * sample_rate),
                local_end=round(float(end_s) * sample_rate),
                conf=None,
            )
        )
    return tuple(words)


def _run(pipeline: Pipeline, samples: np.ndarray, language: str) -> Mapping[str, Any]:
    try:
        result: Mapping[str, Any] = pipeline(
            {"raw": samples, "sampling_rate": NORMALIZED_SAMPLE_RATE},
            generate_kwargs={"language": language, "task": "transcribe"},
            return_timestamps="word",
        )
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            raise TransientError("model ran out of memory on this chunk") from exc
        raise PermanentError("model failed on this chunk") from exc
    except ValueError as exc:
        raise PermanentError("model rejected this chunk") from exc
    return result


def _cached_revision(model_id: str) -> str:
    """The commit of the cached snapshot: the revision recorded as provenance (D-063)."""
    try:
        from huggingface_hub import snapshot_download  # noqa: PLC0415 - lazy: optional at import (D-063)

        return Path(snapshot_download(model_id, local_files_only=True)).name
    except Exception as exc:  # the cache is missing or unreadable: the model cannot be used
        raise PermanentError(f"model {model_id} is not in the local cache") from exc


def _load_pipeline(model_id: str, device: str | None, revision: str) -> Pipeline:
    if device not in (None, "cuda", "cpu"):
        raise PermanentError("device must be cuda, cpu or unset")
    import torch  # noqa: PLC0415 - lazy: torch is an optional extra, absent in CI (D-063)
    from transformers import (  # noqa: PLC0415 - lazy, same reason as torch
        WhisperForConditionalGeneration,
        WhisperProcessor,
        pipeline,
    )

    use_cuda = device == "cuda" or (device is None and torch.cuda.is_available())
    target = "cuda" if use_cuda else "cpu"
    dtype = torch.float16 if use_cuda else torch.float32
    try:
        processor = WhisperProcessor.from_pretrained(
            model_id, revision=revision, local_files_only=True
        )
        model = WhisperForConditionalGeneration.from_pretrained(
            model_id,
            revision=revision,
            local_files_only=True,
            use_safetensors=True,  # no pickle: only safetensors weights are loaded (review)
            dtype=dtype,
        )
        model = model.to(target)  # type: ignore[arg-type]  # transformers types .to loosely
    except OSError as exc:
        raise PermanentError(f"model {model_id} is not in the local cache") from exc
    return pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        chunk_length_s=_CHUNK_SECONDS,
    )
