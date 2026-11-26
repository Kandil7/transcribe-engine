"""TXT renderer (S15): one line per segment, the speaker label first when there is one. Plain text,
no BOM, no RLM marks: those belong to subtitle players, not to text files."""

from transcribe_engine.domain.transcript import CanonicalTranscript

__all__ = ["render_txt"]


def render_txt(transcript: CanonicalTranscript) -> bytes:
    labels = {s.id: s.label for s in transcript.speakers}
    lines = []
    for segment in transcript.segments:
        text = " ".join(word.text for word in segment.words)
        label = labels.get(segment.speaker) if segment.speaker is not None else None
        lines.append(f"{label}: {text}" if label else text)
    return ("".join(f"{line}\n" for line in lines)).encode("utf-8")
