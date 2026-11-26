"""Media admission rules (S09): the format allow-list, and the size and duration limits.

Pure functions, no I/O. The probe adapter supplies the facts (ffprobe's format name, duration and
size); this module decides. A refused file never reaches the normalizer.
"""

from dataclasses import dataclass

from transcribe_engine.domain.jobs import ErrorCode

__all__ = ["ALLOWED_FORMAT_TOKENS", "IngestLimits", "admission_error", "output_error"]

# ffprobe reports a comma-separated list of demuxer names, e.g. "mov,mp4,m4a,3gp,3g2,mj2".
# A file is admitted when one of its names is on this list. HLS ("hls,applehttp") and concat
# are absent on purpose (design: "فحص الملفات وعزل FFmpeg").
ALLOWED_FORMAT_TOKENS: frozenset[str] = frozenset(
    {"mp3", "wav", "flac", "aac", "ogg", "mov", "mp4", "m4a", "matroska", "webm"}
)


@dataclass(frozen=True)
class IngestLimits:
    """Operating limits from the design's starting values (حدود التشغيل المبدئية)."""

    max_duration_ms: int = 3 * 60 * 60 * 1000  # 3 hours
    max_size_bytes: int = 4 * 2**30  # 4 GB


def admission_error(
    format_name: str,
    duration_ms: int,
    size_bytes: int,
    limits: IngestLimits = IngestLimits(),
) -> ErrorCode | None:
    """Return the error code that refuses the file, or None when it is admitted.

    Checked in order: format, duration, size. Each refusal is permanent (no retry).
    """
    if not set(format_name.split(",")) & ALLOWED_FORMAT_TOKENS:
        return ErrorCode.UNSUPPORTED_FORMAT
    if duration_ms > limits.max_duration_ms:
        return ErrorCode.TOO_LONG
    if size_bytes > limits.max_size_bytes:
        return ErrorCode.TOO_LARGE
    return None


def output_error(
    duration_ms: int, size_bytes: int, limits: IngestLimits = IngestLimits()
) -> ErrorCode | None:
    """Refuse the normalized output that exceeds the limits. Review fix (S09): the declared
    duration is not trusted, so the written file is checked."""
    if duration_ms > limits.max_duration_ms:
        return ErrorCode.TOO_LONG
    if size_bytes > limits.max_size_bytes:
        return ErrorCode.TOO_LARGE
    return None
