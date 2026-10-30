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
    diarize_status: str = "",
) -> list[str]:
    """Return QA flag strings for one transcribed video."""
    flags: list[str] = []
    segments = segments or []
    word_segments = word_segments or []
    if diarize_status == "failed":
        flags.append("diarize_failed")

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


def qa_scores(
    duration: float = 0,
    raw: str = "",
    segments: list | None = None,
    word_segments: list | None = None,
) -> dict:
    """Numeric QA metrics for one transcribed video (v1).

    Complements ``qa_checks`` flags: flags catch hard defects, scores
    grade soft quality for corpus filtering / A-B engine comparisons.
    Never raises; missing inputs yield null-style safe values.

    - mean_word_score: mean wav2vec2 alignment confidence in [0, 1],
      None when no aligned words.
    - speech_ratio: segment-covered seconds / media duration in [0, 1+].
      >1 can happen with bad timestamps; the flags gate covers that.
    - empty_ratio: fraction of segments with blank text in [0, 1].
    - repeat_max: highest occurrence count of any 8-word shingle in raw
      (loop-collapse erosion; 31x is lazy series intros, see
      docs/experiments/repeat-artifact-resolution.md).
    - arabic_ratio: fraction of letters in raw written in Arabic script
      in [0, 1]. Script proxy for LID confidence on an Arabic corpus —
      a low value flags code-switched or garbled transcripts. Audio LID
      stays on the roadmap (needs a model).
    """
    segments = segments or []
    word_segments = word_segments or []

    mean_word_score: float | None = None
    scores = [
        float(w.get("score", 0) or 0)
        for w in word_segments
        if isinstance(w, dict) and w.get("score") is not None
    ]
    if scores:
        mean_word_score = round(sum(scores) / len(scores), 3)

    speech_ratio: float | None = None
    empty_ratio: float | None = None
    if segments:
        covered = 0.0
        empties = 0
        for s in segments:
            try:
                covered += max(
                    float(s.get("end", 0) or 0) - float(s.get("start", 0) or 0), 0.0
                )
            except (TypeError, ValueError):
                pass
            if not str(s.get("text", "")).strip():
                empties += 1
        speech_ratio = round(covered / duration, 3) if duration > 0 else None
        empty_ratio = round(empties / len(segments), 3)

    repeat_max = 0
    words = raw.split()
    if len(words) > 8:
        from collections import Counter

        counts = Counter(" ".join(words[i : i + 8]) for i in range(len(words) - 7))
        repeat_max = max(counts.values())

    arabic_ratio: float | None = None
    letters = [ch for ch in raw if ch.isalpha()]
    if letters:

        def _is_arabic(ch: str) -> bool:
            return (
                "\u0600" <= ch <= "\u06ff"
                or "\u0750" <= ch <= "\u077f"
                or "\ufb50" <= ch <= "\ufdff"
                or "\ufe70" <= ch <= "\ufeff"
            )

        arabic_ratio = round(
            sum(1 for ch in letters if _is_arabic(ch)) / len(letters), 3
        )

    return {
        "mean_word_score": mean_word_score,
        "speech_ratio": speech_ratio,
        "empty_ratio": empty_ratio,
        "repeat_max": repeat_max,
        "arabic_ratio": arabic_ratio,
    }
