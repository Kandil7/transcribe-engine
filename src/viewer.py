"""Streamlit dataset viewer (v1): browse videos.jsonl / segments.parquet.

Run from repo root:
    python -m streamlit run src/viewer.py

Purpose-built for two jobs:
1. Inspect the transcription dataset (per video: QA flags, timings, status;
   per segment: times, raw text, word counts).
2. Aid hand-correcting a reference for WER evaluation: select any segment,
   the audio plays exactly that [start,end) window; attach any local mp3.

UI only; pure helpers (flatten_segments, record_status) live here and are
unit-tested without streamlit. JSONL reading is shared: ``load_records``
 comes from ``store.py`` once for all consumers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import streamlit as st

try:  # package execution (tests, python -m src.viewer)
    from .store import load_records
except ImportError:  # streamlit runs this file as a bare script
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.store import load_records


def flatten_segments(rec: dict) -> list[dict]:
    """One record -> segment rows with the fields the viewer shows."""
    rows = []
    for seg in rec.get("segments", []):
        words = seg.get("words", [])
        rows.append(
            {
                "start": round(float(seg.get("start", 0.0)), 2),
                "end": round(float(seg.get("end", 0.0)), 2),
                "speaker": seg.get("speaker", ""),
                "text_raw": seg.get("text", ""),
                "word_count": len(words) if words else len(seg.get("text", "").split()),
            }
        )
    return rows


def record_status(rec: dict) -> dict:
    """Compact chips data for one record."""
    d = rec.get("timings") or {}
    return {
        "video_id": rec.get("video_id", ""),
        "title": rec.get("video_title", ""),
        "duration_s": round(rec.get("duration", 0.0)),
        "segments": len(rec.get("segments", [])),
        "words": len(rec.get("word_segments", [])),
        "align": rec.get("align_status", ""),
        "qa": ",".join(rec.get("qa", [])) or "clean",
        "mean_word_score": (rec.get("qa_scores") or {}).get("mean_word_score"),
        "lid": (
            f"{rec.get('lid_lang', '')} ({rec.get('lid_confidence', 0):.2f})"
            if rec.get("lid_lang")
            else ""
        ),
        "dialect": (
            f"{rec.get('dialect', '')} ({rec.get('dialect_confidence', 0):.2f})"
            if rec.get("dialect")
            else ""
        ),
        "dl_s": round(d.get("download") or 0.0),
        "asr_s": round(d.get("transcribe") or 0.0),
        "total_s": round(d.get("total") or 0.0),
    }


def _fmt_t(t: float) -> str:
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _cli_jsonl() -> str:
    """Honour `streamlit run src/viewer.py -- --jsonl path`."""
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1 :]
        ap = argparse.ArgumentParser()
        ap.add_argument("--jsonl", default="data/output/videos.jsonl")
        ns, _ = ap.parse_known_args(rest)
        return ns.jsonl
    return "data/output/videos.jsonl"


def main() -> None:  # pragma: no cover - streamlit UI
    st.set_page_config(page_title="Transcribe Engine", page_icon="🎙️", layout="wide")
    jsonl = _cli_jsonl()
    recs = load_records(jsonl)
    if not recs:
        st.error(f"No records found at `{jsonl}`. Run the pipeline first.")
        return

    statuses = [record_status(r) for r in recs]
    st.title("🎙️ Transcribe Engine — dataset viewer")

    with st.sidebar:
        st.header("Video")
        labels = [f"{s['video_id']} — {s['title'][:40]}" for s in statuses]
        idx = st.selectbox(
            "Choose a video",
            range(len(labels)),
            format_func=lambda i: labels[i],
        )
        cur, rec = statuses[idx], recs[idx]
        st.caption(f"`{cur['video_id']}`")

        st.divider()
        st.metric("Duration", f"{cur['duration_s'] // 60}m {cur['duration_s'] % 60}s")
        st.metric("Segments / words", f"{cur['segments']} / {cur['words']}")

        qa_col, al_col = st.columns(2)
        if cur["qa"] == "clean":
            qa_col.success("qa: clean")
        else:
            qa_col.error(f"qa: {cur['qa']}")
        al_col.info(f"align: {cur['align']}")
        if cur.get("lid"):
            st.caption(f"lid: {cur['lid']}")
        if cur.get("mean_word_score") is not None:
            st.metric("mean word score", f"{cur['mean_word_score']:.3f}")

        st.divider()
        st.subheader("Timings")
        st.write(
            f"download {cur['dl_s']}s · transcribe {cur['asr_s']}s · total {cur['total_s']}s"
        )

        st.divider()
        st.subheader("Corpus")
        st.write(
            f"{len(statuses)} videos · {sum(s['duration_s'] for s in statuses) // 3600}h audio"
        )
        dirty = [s for s in statuses if s["qa"] != "clean"]
        st.write(f"qa-flagged: {len(dirty)}/{len(statuses)}")
        for s in dirty[:10]:
            st.write(f"- `{s['video_id']}`: {s['qa']}")

        st.divider()
        audio_bytes = None
        up = st.file_uploader(
            "Attach audio (mp3) to play segments", type=["mp3", "m4a", "wav"]
        )
        if up is not None:
            audio_bytes = up.getvalue()

    segs = flatten_segments(rec)
    if not segs:
        st.warning("This record has no segments (failed/empty transcription?).")
        return

    left, right = st.columns([1, 2])

    with right:
        event = st.dataframe(
            segs,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_order=["start", "end", "speaker", "text_raw", "word_count"],
            column_config={
                "word_count": st.column_config.ProgressColumn(
                    "words", min_value=0, max_value=max(s["word_count"] for s in segs)
                ),
            },
        )
        st.caption("Select a row to jump the audio to that segment.")

    with left:
        selected = event.selection.rows if hasattr(event, "selection") else []
        if selected:
            seg = segs[selected[0]]
            st.markdown(f"**Selected** {_fmt_t(seg['start'])}–{_fmt_t(seg['end'])}")
        else:
            seg = segs[0]
        c1, c2 = st.columns(2)
        t0 = c1.number_input(
            "start (s)",
            min_value=0.0,
            max_value=float(cur["duration_s"]),
            value=seg["start"],
            step=0.5,
            key="t0",
        )
        t1 = c2.number_input(
            "end (s)",
            min_value=0.1,
            max_value=max(float(cur["duration_s"]), 0.2),
            value=seg["end"],
            step=0.5,
            key="t1",
        )
        if selected:
            st.markdown(
                f"<div dir='rtl' style='font-size:1.15rem;line-height:1.8'>{seg['text_raw']}</div>",
                unsafe_allow_html=True,
            )

    if audio_bytes:
        st.audio(
            audio_bytes,
            format="audio/mp3",
            start_time=min(t0, float(cur["duration_s"])),
            end_time=min(t1, float(cur["duration_s"])),
        )
    else:
        st.info(
            "No audio attached — add an mp3 in the sidebar to play segment windows."
        )


if __name__ == "__main__":
    main()
