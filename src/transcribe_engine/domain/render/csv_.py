"""CSV renderer (S15): a header and one row per segment. The csv module does the quoting, so a
comma or a quote in the text cannot break the row. Output is UTF-8 with LF line endings."""

import csv
import io

from transcribe_engine.domain.transcript import CanonicalTranscript

__all__ = ["render_csv"]

HEADER = ["start_ms", "end_ms", "speaker", "text"]


def render_csv(transcript: CanonicalTranscript) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    for segment in transcript.segments:
        text = " ".join(word.text for word in segment.words)
        writer.writerow([segment.start_ms, segment.end_ms, segment.speaker or "", text])
    return buffer.getvalue().encode("utf-8")
