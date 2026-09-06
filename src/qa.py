"""QA gates for Transcribe Engine v1 (stdlib only, no heavy deps).

Flags are plain strings stored on ``VideoRecord.qa``; an empty list means
clean. Gates never raise — a flagged record is still written, so one bad
video can't poison a playlist run. Downstream filters on ``qa == []``.
"""

from __future__ import annotations


def qa_checks(
    duration: float = 0,
    raw: str = "",
    segments: list | None = None,
    word_segments: list | None = None,
    align_status: str = "ok",
) -> list[str]:
    """Return QA flag strings for one transcribed video."""
    flags: list[str] = []
    segments = segments or []
    word_segments = word_segments or []

    if not raw.strip():
        flags.append("empty_transcript")
    if not segments:
        flags.append("no_segments")
    if segments and not word_segments and align_status == "ok":
        flags.append("no_words")
    if align_status != "ok":
        flags.append(f"align_{align_status}")

    if segments:
        try:
            span = float(segments[-1].get("end", 0) or 0) - float(
                segments[0].get("start", 0) or 0
            )
        except (TypeError, ValueError):
            span = 0.0
        if (
            duration > 0
            and span > 0
            and abs(span - duration) > max(30.0, 0.10 * duration)
        ):
            flags.append("duration_mismatch")
        bad_order = any(
            float(segments[i].get("start", 0) or 0)
            > float(segments[i].get("end", 0) or 0)
            for i in range(len(segments))
        )
        if bad_order:
            flags.append("bad_timestamps")
    if duration > 0 and duration < 5:
        flags.append("short_audio")
    return flags
