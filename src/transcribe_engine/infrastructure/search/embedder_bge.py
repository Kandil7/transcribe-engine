"""BAAI/bge-m3 dense embedder (S18, D-079), run in-process on this machine with ONNX Runtime.

- The ONNX export in the pinned snapshot (onnx/model.onnx) is used. Its weights are tensor data,
  not pickle, so no pickle is loaded (D-063's security rule). Torch is not needed.
- Read from the local Hugging Face cache, offline, at a pinned commit. A missing model is
  a PermanentError.
- Vectors: the sentence embedding (CLS pooling), L2-normalised here, 1024 dimensions.
- The tokenizer is the model's fast tokenizer (tokenizer.json), so token counts match the vectors.
"""

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
from transformers import AutoTokenizer, PreTrainedTokenizerBase

from transcribe_engine.domain.errors import PermanentError, TransientError

__all__ = ["BGE_M3_DIMENSIONS", "BGE_M3_REVISION", "BgeM3Embedder"]

BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"  # the cached commit (D-079)
BGE_M3_DIMENSIONS = 1024
_MODEL_ID = "BAAI/bge-m3"
_MAX_TOKENS = 512  # the length the model was trained for

Encoder = Callable[[Sequence[str]], list[list[float]]]


class BgeM3Embedder:
    model = _MODEL_ID

    def __init__(
        self,
        *,
        revision: str = BGE_M3_REVISION,
        encoder: Encoder | None = None,
        tokenizer: PreTrainedTokenizerBase | None = None,
    ) -> None:
        self.version = revision
        self._encoder = encoder
        self._tokenizer = tokenizer if tokenizer is not None else _load_tokenizer(revision)
        self._lock = asyncio.Lock()

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False))

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encoder = await self._ensure_encoder()
        try:
            return await asyncio.to_thread(encoder, list(texts))
        except RuntimeError as exc:
            raise TransientError("embedder failed on this batch") from exc

    async def _ensure_encoder(self) -> Encoder:
        async with self._lock:
            if self._encoder is None:
                self._encoder = await asyncio.to_thread(
                    _load_encoder, self._tokenizer, self.version
                )
            return self._encoder


def _load_tokenizer(revision: str) -> PreTrainedTokenizerBase:
    try:
        return AutoTokenizer.from_pretrained(_MODEL_ID, revision=revision, local_files_only=True)
    except OSError as exc:
        raise PermanentError(f"model {_MODEL_ID} is not in the local cache") from exc


def _load_encoder(tokenizer: PreTrainedTokenizerBase, revision: str) -> Encoder:
    import onnxruntime  # noqa: PLC0415 - lazy: optional at import, like the other ML adapters
    from huggingface_hub import snapshot_download  # noqa: PLC0415 - lazy: a cache lookup (D-063)

    try:
        root = Path(snapshot_download(_MODEL_ID, revision=revision, local_files_only=True))
    except OSError as exc:
        raise PermanentError(f"model {_MODEL_ID} is not in the local cache") from exc
    session = onnxruntime.InferenceSession(
        str(root / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"]
    )

    def encode(texts: Sequence[str]) -> list[list[float]]:
        batch = tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=_MAX_TOKENS,
            return_tensors="np",
        )
        outputs = session.run(
            ["sentence_embedding"],
            {
                "input_ids": batch["input_ids"].astype(np.int64),
                "attention_mask": batch["attention_mask"].astype(np.int64),
            },
        )
        pooled = np.asarray(outputs[0], dtype=np.float32)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        normalised = pooled / np.maximum(norms, 1e-12)
        vectors: list[list[float]] = normalised.tolist()
        return vectors

    return encode
