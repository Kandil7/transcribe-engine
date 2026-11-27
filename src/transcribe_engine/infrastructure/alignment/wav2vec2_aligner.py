"""Forced aligner over an Arabic wav2vec2 CTC model (S14, D-070).

Model: parseh/aligner-ar, Apache-2.0.

- The model is an ONNX network that emits one logit row per 20 ms frame (320 samples at 16 kHz).
- The text is normalized with `domain.text.normalize`, mapped to vocabulary ids (a space is the word
  delimiter), and placed on the frames by `domain.ctc.ctc_viterbi`.
- A word spans from the first frame of its first character to the end of its last character.
- Characters that are not in the vocabulary are dropped and cannot be placed; the word keeps its
  original spelling from the raw text.
- An ONNX failure is a PermanentError for the chunk, so the job records a gap, not a silent empty.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Protocol

import numpy as np

from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.chunks import Chunk
from transcribe_engine.domain.ctc import ctc_viterbi
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.merge import RawWord
from transcribe_engine.domain.text import normalize
from transcribe_engine.infrastructure.asr.window import read_window_pcm

__all__ = ["Wav2Vec2Aligner"]


class _Input(Protocol):
    name: str


class OnnxSession(Protocol):
    def get_inputs(self) -> Sequence[_Input]: ...

    def run(self, outputs: None, feed: dict[str, np.ndarray]) -> Sequence[np.ndarray]: ...


FRAME_SAMPLES = 320  # 20 ms at 16 kHz
_PCM_SCALE = 32768.0
_DELIMITER = "|"


class Wav2Vec2Aligner:
    """Aligner port over an ONNX session. `session` is any object with get_inputs() and run()."""

    def __init__(
        self,
        storage: ObjectStorage,
        session: OnnxSession,
        vocab: Mapping[str, int],
        *,
        blank: int,
    ) -> None:
        self._storage = storage
        self._session = session
        self._vocab = vocab
        self._blank = blank
        self._input = session.get_inputs()[0].name

    async def align(
        self, audio_key: str, chunk: Chunk, text: str, *, language: str
    ) -> tuple[RawWord, ...]:
        start = max(0, chunk.start_sample - chunk.pad_before)
        end = chunk.end_sample + chunk.pad_after
        pcm = await read_window_pcm(self._storage, audio_key, start, end)
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / _PCM_SCALE
        normalized = normalize(text)
        ids, placed = self._tokens(normalized.search)
        if not ids:
            return ()
        spans = ctc_viterbi(self._log_probs(samples), ids, self._blank)
        return _words(normalized.raw, normalized.offsets, placed, spans, len(samples))

    def _tokens(self, search: str) -> tuple[list[int], list[tuple[int, bool]]]:
        """Vocabulary ids for the characters that can be placed, and for each one its index in
        `search` and whether it is a space (the word delimiter)."""
        ids: list[int] = []
        placed: list[tuple[int, bool]] = []
        for index, char in enumerate(search):
            is_space = char == " "
            symbol = _DELIMITER if is_space else char
            if symbol in self._vocab:
                ids.append(self._vocab[symbol])
                placed.append((index, is_space))
        return ids, placed

    def _log_probs(self, samples: np.ndarray) -> list[list[float]]:
        if samples.size:
            samples = (samples - samples.mean()) / math.sqrt(samples.var() + 1e-7)
        try:
            logits = self._session.run(None, {self._input: samples[None, :]})[0][0]
        except Exception as exc:  # the model failed on this chunk: permanent for the chunk
            raise PermanentError("aligner failed on this chunk") from exc
        logits = logits - logits.max(axis=1, keepdims=True)
        log_norm = np.log(np.exp(logits).sum(axis=1, keepdims=True))
        scores: list[list[float]] = (logits - log_norm).tolist()
        return scores


def _words(
    raw: str,
    offsets: Sequence[int],
    placed: Sequence[tuple[int, bool]],
    spans: Sequence[tuple[int, int]],
    total_samples: int,
) -> tuple[RawWord, ...]:
    """Group placed characters into words at each space, and convert frames to samples."""
    words: list[RawWord] = []
    group: list[tuple[int, int, int]] = []  # (search index, first frame, last frame)
    for (index, is_space), (first, last) in zip(placed, spans, strict=True):
        if is_space:
            _close(words, group, raw, offsets, total_samples)
            group = []
        else:
            group.append((index, first, last))
    _close(words, group, raw, offsets, total_samples)
    return tuple(words)


def _close(
    words: list[RawWord],
    group: list[tuple[int, int, int]],
    raw: str,
    offsets: Sequence[int],
    total_samples: int,
) -> None:
    if not group:
        return
    first_index, first_frame, _ = group[0]
    last_index, _, last_frame = group[-1]
    text = raw[offsets[first_index] : offsets[last_index] + 1]
    start = min(first_frame * FRAME_SAMPLES, total_samples)
    end = min((last_frame + 1) * FRAME_SAMPLES, total_samples)
    words.append(RawWord(text=text, local_start=start, local_end=end, conf=None))
