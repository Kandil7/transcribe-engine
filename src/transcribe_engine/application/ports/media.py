"""Media ports (S09): probe an uploaded file, and normalize it to 16 kHz mono PCM WAV.

Adapters run FFmpeg tools in a sandbox and translate their failures. A file that cannot be decoded
raises CorruptMediaError; a container or playlist type the pipeline refuses raises
UnsupportedMediaError. Both are permanent. A stalled tool raises TransientError and may retry.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from transcribe_engine.domain.errors import PermanentError

__all__ = [
    "AudioNormalizer",
    "CorruptMediaError",
    "MediaInfo",
    "MediaProbe",
    "NormalizedAudio",
    "UnsupportedMediaError",
]


@dataclass(frozen=True)
class MediaInfo:
    """What ffprobe reports about the container and its first audio stream."""

    format_name: str  # ffprobe's name, e.g. "wav" or "mov,mp4,m4a,3gp,3g2,mj2"
    duration_ms: int
    sample_rate: int
    channels: int
    size_bytes: int


@dataclass(frozen=True)
class NormalizedAudio:
    duration_ms: int
    sample_rate: int
    channels: int
    size_bytes: int


class CorruptMediaError(PermanentError):
    """The file cannot be decoded or has no audio stream. Maps to INVALID_MEDIA."""

    code = "invalid_media"


class UnsupportedMediaError(PermanentError):
    """A playlist or container refused before or after probing. Maps to UNSUPPORTED_FORMAT."""

    code = "unsupported_format"


class MediaProbe(Protocol):
    async def probe(self, path: Path) -> MediaInfo:
        """Read the format from the file's content, never from its name."""
        ...


class AudioNormalizer(Protocol):
    async def to_pcm16_mono_16k(self, src: Path, dst: Path, *, timeout_s: float) -> NormalizedAudio:
        """Write 16 kHz mono 16-bit PCM WAV to `dst`. `timeout_s` bounds the conversion."""
        ...
