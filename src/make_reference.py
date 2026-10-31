"""Build a segment-aligned hand-correction template for WER evaluation.

For one video, pull the ar auto-captions (which carry per-word
timestamps in their inline ``<t><c> word</c>`` tags), assign each word
to the pipeline segment whose window contains it, and write one line per
segment::

    [0:00.1-0:29.6] word1 word2 ...

The user corrects each line against the audio (the Streamlit viewer
plays exactly those windows via ``st.audio(start_time=...)``), saves the
file as ``<video>_reference.txt``, and scores it with
``python -m src.score_wer <video_id> <file>`` — which understands the
same timestamps and reports per-segment WER.

Usage:
    python -m src.make_reference <video_id> [--out data/eval/...]

Pure helpers (``parse_vtt_words``, ``assign_to_segments``) are
unit-tested; only ``fetch_vtt`` touches the network.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Inline tag written by YouTube rolling captions: each NEW word appears
# exactly once in the file inside such a tag, carrying its start time.
_WORD_TAG = re.compile(r"<(\d\d:\d\d:\d\d\.\d+)><c> ([^<]+)</c>")


def parse_vtt_words(vtt_text: str) -> list[tuple[float, str]]:
    """Extract (start_seconds, word) from tagged words in VTT text, in order."""
    words: list[tuple[float, str]] = []
    for line in vtt_text.splitlines():
        for m in _WORD_TAG.finditer(line):
            t = _ts(m.group(1))
            w = m.group(2).strip()
            if w:
                words.append((t, w))
    return words


def _ts(s: str) -> float:
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def assign_to_segments(
    words: list[tuple[float, str]], segments: list[dict]
) -> list[str]:
    """Group words under the pipeline segments that contain them.

    Returns one joined text per segment (same order as ``segments``).
    A word outside every segment window goes to the nearest segment by
    midpoint distance; segments with no words yield "".
    """
    if not segments:
        return []
    texts: list[list[str]] = [[] for _ in segments]
    for t, w in words:
        best = None
        best_dist = float("inf")
        for i, s in enumerate(segments):
            start = float(s.get("start", 0) or 0)
            end = float(s.get("end", 0) or 0)
            if start <= t < end:
                best = i
                break
            dist = min(abs(t - start), abs(t - end))
            if dist < best_dist:
                best_dist = dist
                best = i
        texts[best].append(w)
    return [" ".join(ws) for ws in texts]


def _fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:04.1f}"


def format_template(segments: list[dict], texts: list[str]) -> str:
    lines = []
    for s, text in zip(segments, texts):
        t0 = float(s.get("start", 0) or 0)
        t1 = float(s.get("end", 0) or 0)
        lines.append(f"[{_fmt(t0)}-{_fmt(t1)}] {text}".rstrip())
    return "\n".join(lines) + "\n"


def fetch_vtt(video_id: str) -> str:
    """Download the ar auto-captions VTT for a video (yt-dlp)."""
    import glob
    import os
    import subprocess
    import sys
    import tempfile

    tmp = tempfile.mkdtemp(prefix="mkref_")
    outtmpl = os.path.join(tmp, video_id + ".%(ext)s")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--quiet",
            "--no-warnings",
            "--no-playlist",
            "--skip-download",
            "--write-automatic-sub",
            "--sub-langs",
            "ar",
            "--sub-format",
            "vtt",
            "-o",
            outtmpl,
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        check=True,
    )
    files = glob.glob(os.path.join(tmp, video_id + "*.vtt"))
    if not files:
        raise SystemExit(f"no ar auto-captions for {video_id}")
    return Path(files[0]).read_text(encoding="utf-8", errors="replace")


def main(argv=None) -> str:
    ap = argparse.ArgumentParser(description="segment-aligned WER reference template")
    ap.add_argument("video_id")
    ap.add_argument("--jsonl", default="data/output/videos.jsonl")
    ap.add_argument(
        "--out",
        default="",
        help="output path (default data/eval/<id>_reference_template.txt)",
    )
    ns = ap.parse_args(argv)

    try:
        from .score_wer import load_video
    except ImportError:
        from score_wer import load_video  # type: ignore

    rec = load_video(ns.jsonl, ns.video_id)
    segments = rec.get("segments", [])
    if not segments:
        raise SystemExit(f"record {ns.video_id} has no segments")
    words = parse_vtt_words(fetch_vtt(ns.video_id))
    texts = assign_to_segments(words, segments)
    out = Path(ns.out or f"data/eval/{ns.video_id}_reference_template.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_template(segments, texts), encoding="utf-8")
    filled = sum(1 for t in texts if t.strip())
    print(f"template written: {out} ({len(segments)} lines, {filled} prefilled)")
    return str(out)


if __name__ == "__main__":
    main()
