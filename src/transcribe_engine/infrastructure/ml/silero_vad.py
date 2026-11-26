"""Silero VAD adapter (S11): speech regions of the normalized WAV, in integer samples.

The model ships inside the silero-vad package, so no network is needed. The WAV is streamed from
storage into the scratch directory and read there; it is never held whole in memory by the adapter
beyond the sample array. Needs the `ml` extra (torch, silero-vad, numpy).
"""

import asyncio
import importlib.metadata
import uuid
import wave
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.application.ports.vad import VadResult
from transcribe_engine.domain.chunks import NORMALIZED_SAMPLE_RATE, SpeechRegion
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.vad import VadParams

if TYPE_CHECKING:  # numpy is in the ml extra only; typing needs no runtime import
    import numpy as np

__all__ = ["SileroVad"]

NAME = "silero-vad"
_INT16_SCALE = 32768.0


@cache
def _model() -> object:
    silero = importlib.import_module("silero_vad")
    return silero.load_silero_vad()


def _revision() -> str:
    try:
        return importlib.metadata.version("silero-vad")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


class SileroVad:
    name = NAME
    revision = _revision()

    def __init__(self, storage: ObjectStorage, scratch: Path) -> None:
        self._storage = storage
        self._scratch = scratch

    async def analyze(self, audio_key: str, params: VadParams) -> VadResult:
        """Port method used by PrepareChunks: the total length and the speech regions."""
        local = await self._download(audio_key)
        try:
            samples = _read_samples(local)
        finally:
            local.unlink(missing_ok=True)
        regions = await self._regions(samples, params)
        return VadResult(total_samples=len(samples), regions=regions)

    async def detect(self, audio_key: str, params: VadParams) -> tuple[SpeechRegion, ...]:
        local = await self._download(audio_key)
        try:
            samples = _read_samples(local)
        finally:
            local.unlink(missing_ok=True)
        return await self._regions(samples, params)

    async def _download(self, audio_key: str) -> Path:
        self._scratch.mkdir(parents=True, exist_ok=True)
        target = self._scratch / f"vad-{uuid.uuid4().hex}.wav"
        with target.open("wb") as handle:
            async for chunk in self._storage.stream(audio_key):
                handle.write(chunk)
        return target

    async def _regions(self, samples: "np.ndarray", params: VadParams) -> tuple[SpeechRegion, ...]:
        return await asyncio.to_thread(_detect_sync, samples, params)


def _detect_sync(samples: "np.ndarray", params: VadParams) -> tuple[SpeechRegion, ...]:
    torch = importlib.import_module("torch")
    silero = importlib.import_module("silero_vad")
    if len(samples) == 0:
        return ()
    audio = torch.from_numpy(samples)
    stamps = silero.get_speech_timestamps(
        audio,
        _model(),
        threshold=params.threshold,
        sampling_rate=NORMALIZED_SAMPLE_RATE,
        min_speech_duration_ms=params.min_speech_ms,
        min_silence_duration_ms=params.min_silence_ms,
        return_seconds=False,
    )
    return tuple(
        SpeechRegion(int(stamp["start"]), int(stamp["end"]))
        for stamp in stamps
        if int(stamp["end"]) > int(stamp["start"])
    )


def _read_samples(path: Path) -> "np.ndarray":
    """16 kHz mono 16-bit PCM from the normalized WAV, as float32 in [-1, 1)."""
    numpy = importlib.import_module("numpy")
    try:
        with wave.open(str(path), "rb") as handle:
            if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (
                NORMALIZED_SAMPLE_RATE,
                1,
                2,
            ):
                raise PermanentError("normalized audio is not 16 kHz mono 16-bit PCM")
            raw = handle.readframes(handle.getnframes())
    except wave.Error as exc:
        raise PermanentError("normalized audio is not a WAV file") from exc
    samples: np.ndarray = numpy.frombuffer(raw, dtype="<i2").astype("float32") / _INT16_SCALE
    return samples
