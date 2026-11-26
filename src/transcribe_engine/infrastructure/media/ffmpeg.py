"""FFmpeg normalizer for AudioNormalizer (S09): any admitted file to 16 kHz mono PCM s16le WAV.

Runs in the same sandbox as the probe: list argv, `-protocol_whitelist file`, no shell, a hard
timeout chosen by the caller in proportion to the duration. The output is read back with the
stdlib `wave` module, so the sample rate, channel count and width are checked, not assumed.
"""

import wave
from pathlib import Path

from transcribe_engine.application.ports.media import CorruptMediaError, NormalizedAudio
from transcribe_engine.domain.media_rules import IngestLimits
from transcribe_engine.infrastructure.media.sandbox import run_tool

__all__ = ["FfmpegNormalizer"]

SAMPLE_RATE = 16_000
_MS_PER_S = 1000


class FfmpegNormalizer:
    def __init__(
        self,
        binary: tuple[str, ...] = ("ffmpeg",),
        max_duration_ms: int = IngestLimits().max_duration_ms,
    ) -> None:
        self._binary = binary
        # Clip one second past the limit, in whole seconds, so an overlong file is seen and refused
        # as TOO_LONG by output_error rather than silently truncated to exactly the limit (review).
        self._clip_s = max_duration_ms // 1000 + 1

    async def to_pcm16_mono_16k(self, src: Path, dst: Path, *, timeout_s: float) -> NormalizedAudio:
        argv = [
            *self._binary,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-protocol_whitelist",
            "file",
            "-i",
            str(src),
            "-t",
            str(self._clip_s),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "-y",
            str(dst),
        ]
        code, _ = await run_tool(argv, timeout_s)
        if code != 0:
            raise CorruptMediaError("ffmpeg could not convert the file")
        return _read_back(dst)


def _read_back(path: Path) -> NormalizedAudio:
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            frames = handle.getnframes()
    except (wave.Error, EOFError) as exc:
        raise CorruptMediaError("normalized output is not a WAV file") from exc
    if (rate, channels, width) != (SAMPLE_RATE, 1, 2):
        raise CorruptMediaError("normalized output is not 16 kHz mono 16-bit PCM")
    return NormalizedAudio(
        duration_ms=round(frames * _MS_PER_S / rate),
        sample_rate=rate,
        channels=channels,
        size_bytes=path.stat().st_size,
    )
