"""ffprobe adapter for MediaProbe (S09). ffprobe decides the format; the file name never does.

Refusals before any process starts: a file outside the work directory (a caller bug), and a
playlist or concat file, detected by its first bytes (design: magic bytes are a pre-filter only).
Then ffprobe runs with `-protocol_whitelist file`, so network and other protocols are refused.
"""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from transcribe_engine.application.ports.media import (
    CorruptMediaError,
    MediaInfo,
    UnsupportedMediaError,
)
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.infrastructure.media.sandbox import run_tool

__all__ = ["FfprobeMediaProbe"]

_PLAYLIST_MARKERS = (b"#EXTM3U", b"ffconcat")
_HEAD_BYTES = 512
_MS = Decimal(1000)


class FfprobeMediaProbe:
    def __init__(
        self,
        work_root: Path,
        binary: tuple[str, ...] = ("ffprobe",),
        timeout_s: float = 30.0,
    ) -> None:
        self._work_root = work_root.resolve()
        self._binary = binary
        self._timeout_s = timeout_s

    async def probe(self, path: Path) -> MediaInfo:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._work_root):
            raise PermanentError("media path is outside the work directory")
        with resolved.open("rb") as handle:
            head = handle.read(_HEAD_BYTES)
        if any(marker in head.lstrip() for marker in _PLAYLIST_MARKERS):
            raise UnsupportedMediaError("playlists and concat files are not accepted")

        argv = [
            *self._binary,
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(resolved),
        ]
        code, stdout = await run_tool(argv, self._timeout_s)
        if code != 0:
            raise CorruptMediaError("ffprobe could not read the file")
        return _media_info(stdout, resolved.stat().st_size)


def _media_info(stdout: bytes, size_bytes: int) -> MediaInfo:
    try:
        data: dict[str, Any] = json.loads(stdout)
        fmt = data["format"]
        audio = next(s for s in data["streams"] if s.get("codec_type") == "audio")
        duration_ms = int(
            (Decimal(str(fmt["duration"])) * _MS).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )
        return MediaInfo(
            format_name=str(fmt["format_name"]),
            duration_ms=duration_ms,
            sample_rate=int(audio["sample_rate"]),
            channels=int(audio["channels"]),
            size_bytes=size_bytes,
        )
    except (ValueError, KeyError, TypeError, StopIteration, ArithmeticError) as exc:
        raise CorruptMediaError("ffprobe output has no usable audio stream") from exc
