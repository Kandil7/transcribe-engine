"""Markdown renderer (S15): a heading with the transcript id, then one bold speaker label and the
start time per turn. Times are integer ms in the model and are shown as HH:MM:SS here."""

from transcribe_engine.domain.transcript import CanonicalTranscript

__all__ = ["render_md"]


def render_md(transcript: CanonicalTranscript) -> bytes:
    labels = {s.id: s.label for s in transcript.speakers}
    parts = [f"# {transcript.transcript_id}\n\n"]
    for segment in transcript.segments:
        text = " ".join(word.text for word in segment.words)
        label = labels.get(segment.speaker, "") if segment.speaker is not None else ""
        clock = _clock(segment.start_ms)
        head = f"**{label}** " if label else ""
        parts.append(f"{head}`{clock}` {text}\n\n")
    return "".join(parts).encode("utf-8")


def _clock(ms: int) -> str:
    seconds = ms // 1000
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
