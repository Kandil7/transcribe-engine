"""S15 plain formats: TXT, Markdown and CSV render from the canonical transcript (ADR-0004).
The spec sets no AC of its own for these, so each test pins the layout and checks a positive
control: the same transcript with a different speaker produces different output.
Imports happen inside helpers so the module collects before the code exists.
"""

import csv
import importlib
import io
from dataclasses import replace
from types import ModuleType

from tests.unit.render.test_srt import two_speaker_transcript


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def test_txt_one_line_per_speaker_turn() -> None:
    """TXT: one line per segment, the speaker label first. Positive control: the two speakers
    differ, so both labels appear."""
    txt = _mod("transcribe_engine.domain.render.txt")
    body = txt.render_txt(two_speaker_transcript())
    assert body == ("SPEAKER_01: مرحبا بيكم في البرنامج.\nSPEAKER_02: أهلا بيك يا أستاذ\n").encode()


def test_md_heading_and_turns() -> None:
    """Markdown: a heading with the transcript id, then one bold label and timestamp per turn."""
    md = _mod("transcribe_engine.domain.render.md")
    body = md.render_md(two_speaker_transcript()).decode("utf-8")
    assert body.startswith("# tr-1\n")
    assert "**SPEAKER_01** `00:00:00`" in body
    assert "**SPEAKER_02** `00:00:02`" in body


def test_csv_header_rows_and_quoting() -> None:
    """CSV: a header, one row per segment, and a text with a comma and quotes survives a round
    trip. Positive control: the plain fixture's rows carry each speaker id."""
    csv_mod = _mod("transcribe_engine.domain.render.csv_")
    transcript = two_speaker_transcript()
    rows = list(csv.reader(io.StringIO(csv_mod.render_csv(transcript).decode("utf-8"))))
    assert rows[0] == ["start_ms", "end_ms", "speaker", "text"]
    assert len(rows) == 1 + len(transcript.segments)
    assert rows[1][2] == "S1"
    assert rows[2][2] == "S2"
    first_word = transcript.segments[0].words[0]
    tricky_text = 'قال "يا جماعة"، ازيك'
    tricky = replace(
        transcript,
        segments=(replace(transcript.segments[0], words=(replace(first_word, text=tricky_text),)),),
    )
    rows = list(csv.reader(io.StringIO(csv_mod.render_csv(tricky).decode("utf-8"))))
    assert rows[1][3] == tricky_text
