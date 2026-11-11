"""WER/CER scorer: hand reference vs pipeline transcript (v1 eval).

Usage:
    python -m src.score_wer <video_id> <reference.txt> [--slice 2:00-6:00]

The reference file is plain Arabic text. Bare lines are compared against the
whole video's transcript_raw; with `--slice A-B` (mm:ss or h:mm:ss) the
hypothesis is restricted to pipeline segments overlapping the window, so the
reference may be transcribed for just that window.

Both sides go through normalize_ar (versioned fold) before scoring, so
diacritics/hamza/alef variants do not count as errors. Dialect words count
normally. Stdlib only: no jedi dependencies.

Outputs WER, CER, and length stats; also a short correction-oriented
summary (deletions/insertions/substitutions) via per-word alignment.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from .store import load_video


def _edit_alignment(hyp: list[str], ref: list[str]) -> tuple[int, int, int]:
    """Word-level DP returning (subs, deletions, insertions).

    Standard WER conventions: ref words not matched by hyp = deletions,
    hyp words not matching ref = insertions.
    """
    n, m = len(hyp), len(ref)
    # rows = hyp index i, cols = ref index j.
    # Value = (edit_cost, subs, dels, ins).
    table = [[(0, 0, 0, 0)] * (m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        table[0][j] = (j, 0, j, 0)
    for i in range(1, n + 1):
        table[i][0] = (i, 0, 0, i)
    for i in range(1, n + 1):
        hw = hyp[i - 1]
        for j in range(1, m + 1):
            sub_cost = 0 if hw == ref[j - 1] else 1
            c_sub = (
                table[i - 1][j - 1][0] + sub_cost,
                table[i - 1][j - 1][1] + (1 if sub_cost else 0),
                table[i - 1][j - 1][2],
                table[i - 1][j - 1][3],
            )
            c_del = (
                table[i - 1][j][0] + 1,
                table[i - 1][j][1],
                table[i - 1][j][2] + 1,
                table[i - 1][j][3],
            )
            c_ins = (
                table[i][j - 1][0] + 1,
                table[i][j - 1][1],
                table[i][j - 1][2],
                table[i][j - 1][3] + 1,
            )
            table[i][j] = min(c_sub, c_del, c_ins)
    return table[n][m][1], table[n][m][2], table[n][m][3]


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _parse_t(s: str) -> float:
    s = s.strip()
    if "." in s:
        head, frac = s.split(".", 1)
        frac = float("0." + frac)
    else:
        head, frac = s, 0.0
    parts = head.split(":")
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"bad timestamp {s!r}")
    t = 0.0
    for v in parts:
        t = t * 60 + int(v)
    return t + frac


def _parse_slice(s: str) -> tuple[float, float]:
    a, b = s.split("-", 1) if "-" in s else (None, None)
    if a is None:
        raise ValueError("--slice expects A-B like 2:00-6:00")
    return _parse_t(a), _parse_t(b)


def hypothesis_for(d: dict, window: tuple[float, float] | None) -> str:
    if not window:
        return d.get("transcript_raw", "")
    t0, t1 = window
    parts = [
        s["text"] for s in d.get("segments", []) if s["end"] > t0 and s["start"] < t1
    ]
    return " ".join(parts)


def score(hyp: str, ref: str) -> dict:
    from .normalize_ar import normalize_ar

    hn = normalize_ar(hyp).split()
    rn = normalize_ar(ref).split()
    subs, dels, ins = _edit_alignment(hn, rn)
    wer = (subs + dels + ins) / max(len(rn), 1)
    hc = normalize_ar(hyp).replace(" ", "")
    rc = normalize_ar(ref).replace(" ", "")
    cer = edit_distance(hc, rc) / max(len(rc), 1)
    return {
        "wer": wer,
        "cer": cer,
        "ref_words": len(rn),
        "hyp_words": len(hn),
        "substitutions": subs,
        "deletions": dels,
        "insertions": ins,
    }


_TIMED_LINE = re.compile(r"^\[([\d:.]+)-([\d:.]+)\]\s*(.*)$")


def parse_reference(text: str) -> tuple[list[tuple[float, float, str]], str]:
    """Detect a timestamped reference (``[A-B] text`` lines).

    Returns ``(lines, flattened_text)``; ``lines`` is empty for plain
    references, in which case ``flattened_text`` is the whole input.
    """
    lines: list[tuple[float, float, str]] = []
    matched_any = False
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = _TIMED_LINE.match(s)
        if m:
            matched_any = True
            lines.append((_parse_t(m.group(1)), _parse_t(m.group(2)), m.group(3)))
        elif matched_any:
            lines.append((0.0, 0.0, s))  # untimed line inside a timed ref
    if not matched_any:
        return [], text
    return lines, " ".join(t for _, _, t in lines)


def score_reference_lines(
    rec: dict, lines: list[tuple[float, float, str]]
) -> list[dict]:
    """Per-line WER: each reference line vs the hyp segments in its window."""
    out = []
    for t0, t1, text in lines:
        hyp = hypothesis_for(rec, (t0, t1)) if t1 > t0 else ""
        m = score(hyp, text)
        m["start"], m["end"] = t0, t1
        m["text"] = text
        out.append(m)
    return out


def main(argv=None) -> dict:
    p = argparse.ArgumentParser(description="WER/CER vs hand reference")
    p.add_argument("video_id")
    p.add_argument("reference", help="path to plain-text Arabic reference")
    p.add_argument("--jsonl", default="data/output/videos.jsonl")
    p.add_argument("--slice", default="", help="A-B window, e.g. 2:00-6:00")
    args = p.parse_args(argv)

    d = load_video(args.jsonl, args.video_id)
    window = _parse_slice(args.slice) if args.slice else None
    hyp = hypothesis_for(d, window)
    ref = Path(args.reference).read_text(encoding="utf-8")
    if not ref.strip():
        raise SystemExit("reference file is empty")
    lines, flat = parse_reference(ref)
    m = score(hyp, flat)
    m["video_id"] = args.video_id
    print(
        "WER={wer:.3f} CER={cer:.3f} ref_words={ref_words} hyp_words={hyp_words}\n"
        "substitutions={substitutions} deletions={deletions} insertions={insertions}".format(
            **m
        )
    )
    if lines:
        per_line = score_reference_lines(d, lines)
        scored = [x for x in per_line if x["ref_words"] > 0]
        scored.sort(key=lambda x: -x["wer"])
        print(f"\nper-segment WER ({len(scored)} lines), worst 5:")
        for x in scored[:5]:
            print(
                f"  {_fmt_line(x['start'])}-{_fmt_line(x['end'])} "
                f"WER={x['wer']:.2f} ({x['substitutions']}s {x['deletions']}d {x['insertions']}i) "
                f"{x['text'][:60]}"
            )
    return m


def _fmt_line(t: float) -> str:
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


if __name__ == "__main__":
    main()
