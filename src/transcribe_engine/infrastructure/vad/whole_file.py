"""Plumbing VAD (S10, D-035): one speech region covering the whole normalized file.

Real speech detection arrives with S11. This adapter reads only the WAV header through storage (no
download) and reports the sample count, so the chunk plan and the pipeline can run end to end.
"""

from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.application.ports.vad import VadResult
from transcribe_engine.domain.chunks import SpeechRegion
from transcribe_engine.domain.errors import PermanentError

__all__ = ["WholeFileVad"]

_HEADER_BYTES = 64 * 1024  # enough for RIFF plus any LIST chunks before `data`


class WholeFileVad:
    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage

    async def analyze(self, audio_key: str) -> VadResult:
        info = await self._storage.head(audio_key)
        if info is None:
            raise PermanentError("normalized audio is missing")
        header = await self._storage.read_range(audio_key, 0, min(info.size, _HEADER_BYTES))
        data_bytes = _data_bytes(header, info.size)
        total = data_bytes // 2  # 16-bit mono PCM: two bytes per sample
        regions = (SpeechRegion(0, total),) if total > 0 else ()
        return VadResult(total_samples=total, regions=regions)


def _data_bytes(header: bytes, file_size: int) -> int:
    """Size of the `data` chunk, read from a RIFF/WAVE header. Clipped to the bytes that exist."""
    if header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise PermanentError("normalized audio is not a WAV file")
    position = 12
    while position + 8 <= len(header):
        chunk_id = header[position : position + 4]
        size = int.from_bytes(header[position + 4 : position + 8], "little")
        if chunk_id == b"data":
            available = file_size - (position + 8)
            return max(0, min(size, available))
        position += 8 + size + (size & 1)
    raise PermanentError("normalized audio has no data chunk in its header")
