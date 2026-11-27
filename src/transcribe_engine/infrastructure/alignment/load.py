"""Load the Arabic forced aligner at its pinned revision (S14, D-070).

The model is an ONNX file plus a JSON vocabulary. The revision is pinned in settings and is never
"latest". A model that is not in the cache is downloaded once from the hub (the owner approved this
model in D-070). The access token, if any, comes from the environment, never from a file.
"""

import json
from pathlib import Path
from typing import Any

from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.infrastructure.alignment.wav2vec2_aligner import Wav2Vec2Aligner

__all__ = ["load_wav2vec2_aligner"]

_MODEL_FILE = "model.int8.onnx"
_VOCAB_FILE = "vocab.json"
_PAD = "<pad>"


def load_wav2vec2_aligner(storage: ObjectStorage, model_id: str, revision: str) -> Wav2Vec2Aligner:
    import onnxruntime  # noqa: PLC0415 - lazy: optional at import, like the other ML adapters (D-063)
    from huggingface_hub import snapshot_download  # noqa: PLC0415 - lazy: a network step (D-070)

    try:
        root = Path(snapshot_download(model_id, revision=revision))
    except Exception as exc:  # no network and no cache, or an unknown revision
        raise PermanentError(f"aligner {model_id} at {revision} is not available") from exc
    vocab = _read_vocab(root / _VOCAB_FILE)
    session: Any = onnxruntime.InferenceSession(
        str(root / _MODEL_FILE), providers=["CPUExecutionProvider"]
    )
    return Wav2Vec2Aligner(storage, session, vocab, blank=vocab[_PAD])


def _read_vocab(path: Path) -> dict[str, int]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PermanentError("aligner vocabulary is unreadable") from exc
    if not isinstance(raw, dict) or _PAD not in raw:
        raise PermanentError("aligner vocabulary has no blank token")
    return {str(symbol): int(index) for symbol, index in raw.items()}
