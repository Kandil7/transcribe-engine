"""Read a chunk's padded window of the normalized audio from storage (S10, S12).

One Range GET for the samples, no per-chunk file (S10). The normalized file is 16-bit mono PCM at
NORMALIZED_SAMPLE_RATE (ADR-0003). Shared by the ASR adapters so the window arithmetic exists once.
"""

import struct

from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.errors import PermanentError

__all__ = ["BYTES_PER_SAMPLE", "read_window_pcm"]

HEADER_PROBE_BYTES = 4096
BYTES_PER_SAMPLE = 2  # 16-bit PCM, mono (ADR-0003)


async def read_window_pcm(storage: ObjectStorage, audio_key: str, start: int, end: int) -> bytes:
    """Raw little-endian PCM for samples [start, end) of the normalized file."""
    head = await storage.read_range(audio_key, 0, HEADER_PROBE_BYTES)
    offset = data_offset(head)
    return await storage.read_range(
        audio_key, offset + start * BYTES_PER_SAMPLE, (end - start) * BYTES_PER_SAMPLE
    )


def data_offset(head: bytes) -> int:
    """Byte offset of the PCM samples in a RIFF/WAVE file, found from its chunk list."""
    if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        raise PermanentError("normalized audio is not a WAV file")
    pos = 12
    while pos + 8 <= len(head):
        chunk_id = head[pos : pos + 4]
        (size,) = struct.unpack("<I", head[pos + 4 : pos + 8])
        if chunk_id == b"data":
            return pos + 8
        pos += 8 + size + (size & 1)
    raise PermanentError("normalized audio has no data chunk in its header")
