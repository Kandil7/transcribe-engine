"""Shared helpers for the subtitle renderers (S15): right-to-left marks and timestamps."""

from transcribe_engine.domain.render.cues import SENTENCE_PUNCTUATION

__all__ = ["RLM", "rtl_line", "timestamp"]

RLM = chr(0x200F)  # right-to-left mark


def rtl_line(text: str) -> str:
    """Start a line with an RLM so a player keeps Arabic right-to-left. Add one after trailing
    punctuation too, so the mark does not move the period to the wrong side."""
    stripped = text.rstrip()
    trailing = RLM if stripped and stripped[-1] in SENTENCE_PUNCTUATION else ""
    return RLM + text + trailing


def timestamp(ms: int, separator: str) -> str:
    """HH:MM:SS<sep>mmm. `separator` is "," for SRT and "." for WebVTT."""
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"
