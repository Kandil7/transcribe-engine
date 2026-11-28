"""BAAI/bge-m3 dense embedder (S18, D-079), run in-process on this machine with ONNX Runtime.

- The ONNX export in the pinned snapshot (onnx/model.onnx) is used. Its weights are tensor data, not
  pickle, so no pickle is loaded (D-063's security rule). Torch is not needed.
- Read from the local Hugging Face cache, offline, at a pinned commit. A missing model is a
  PermanentError.
- Vectors: the sentence embedding (CLS pooling), L2-normalised here, 1024 dimensions.
- `model` is the identity of the vectors: the model name and the pinned revision. A new revision
  is a new identity, so its vectors are never mixed with the old ones (D-079).
- numpy, transformers and onnxruntime are imported where they are used, so importing this module
  costs nothing on a deployment without the search model.
"""

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from transcribe_engine.domain.errors import PermanentError, TransientError

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizerBase

__all__ = ["BGE_M3_DIMENSIONS", "BGE_M3_REVISION", "BgeM3Embedder"]

BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"  # the cached commit (D-079)
BGE_M3_DIMENSIONS = 1024
_MODEL_ID = "BAAI/bge-m3"
_MAX_TOKENS = 512  # the length the model was trained for
_BATCH = 16  # texts per session run: bounds the memory of one inference

Encoder = Callable[[Sequence[str]], list[list[float]]]


class BgeM3Embedder:
    def __init__(self, *, revision: str = BGE_M3_REVISION) -> None:
        self.version = revision
        self.model = f"{_MODEL_ID}@{revision}"
        self._tokenizer = _load_tokenizer(revision)
        self._encoder: Encoder | None = None
        self._lock = asyncio.Lock()

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False))

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encoder = await self._ensure_encoder()
        try:
            return await asyncio.to_thread(encoder, list(texts))
        except (TransientError, PermanentError):
            raise
        except Exception as exc:  # onnxruntime raises its own exception types, not RuntimeError
            raise TransientError("embedder failed on this batch") from exc

    async def _ensure_encoder(self) -> Encoder:
        async with self._lock:
            if self._encoder is None:
                self._encoder = await asyncio.to_thread(
                    _load_encoder, self._tokenizer, self.version
                )
            return self._encoder


def _load_tokenizer(revision: str) -> "PreTrainedTokenizerBase":
    from transformers import AutoTokenizer  # noqa: PLC0415 - lazy: only when search is on (D-079)

    try:
        return AutoTokenizer.from_pretrained(_MODEL_ID, revision=revision, local_files_only=True)
    except OSError as exc:
        raise PermanentError(f"model {_MODEL_ID} is not in the local cache") from exc


def _load_encoder(tokenizer: "PreTrainedTokenizerBase", revision: str) -> Encoder:
    import numpy as np  # noqa: PLC0415 - lazy: numpy is an optional extra (D-063)
    import onnxruntime  # noqa: PLC0415 - lazy, like the other ML adapters
    from huggingface_hub import snapshot_download  # noqa: PLC0415 - a cache lookup (D-063)

    try:
        root = Path(snapshot_download(_MODEL_ID, revision=revision, local_files_only=True))
    except OSError as exc:
        raise PermanentError(f"model {_MODEL_ID} is not in the local cache") from exc
    session = onnxruntime.InferenceSession(
        str(root / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"]
    )

    def encode_batch(batch_texts: list[str]) -> list[list[float]]:
        batch = tokenizer(
            batch_texts,
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

    def encode(texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            out.extend(encode_batch(list(texts[start : start + _BATCH])))
        return out

    return encode
