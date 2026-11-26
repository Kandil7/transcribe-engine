"""SRT renderer (S15, AC-5, AC-6): UTF-8 with a BOM, every text line starts with U+200F."""

from collections.abc import Sequence

from transcribe_engine.domain.render._lines import rtl_line, timestamp
from transcribe_engine.domain.render.cues import Cue

__all__ = ["render_srt"]

BOM = "﻿"


def render_srt(cues: Sequence[Cue], *, bom: bool = True) -> bytes:
    blocks = []
    for number, cue in enumerate(cues, start=1):
        text = "\n".join(rtl_line(line) for line in cue.lines)
        blocks.append(
            f"{number}\n{timestamp(cue.start_ms, ',')} --> {timestamp(cue.end_ms, ',')}\n{text}\n\n"
        )
    return ((BOM if bom else "") + "".join(blocks)).encode("utf-8")
