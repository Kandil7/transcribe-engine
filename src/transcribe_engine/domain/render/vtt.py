"""WebVTT renderer (S15, AC-5): voice tags for speakers, RTL marks on every text line."""

from collections.abc import Sequence

from transcribe_engine.domain.render._lines import rtl_line, timestamp
from transcribe_engine.domain.render.cues import Cue

__all__ = ["render_vtt"]


def render_vtt(cues: Sequence[Cue], *, speakers: bool = True) -> str:
    blocks = ["WEBVTT\n\n"]
    for cue in cues:
        tag = f"<v {cue.speaker_label}>" if speakers and cue.speaker_label else ""
        first, *rest = [rtl_line(line) for line in cue.lines]
        text = "\n".join([tag + first, *rest])
        blocks.append(
            f"{timestamp(cue.start_ms, '.')} --> {timestamp(cue.end_ms, '.')}\n{text}\n\n"
        )
    return "".join(blocks)
