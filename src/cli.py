"""CLI for Transcribe Engine v1: single video or playlist → JSONL → Parquet."""

from __future__ import annotations

import argparse
import os

try:
    from .jsonl_to_parquet import main as jsonl_to_parquet_main
    from .pipeline import CHECKPOINT_DB, OUTPUT_JSONL, process_playlist, process_video
except ImportError:  # script-style execution
    from jsonl_to_parquet import main as jsonl_to_parquet_main  # type: ignore
    from pipeline import CHECKPOINT_DB, OUTPUT_JSONL, process_playlist, process_video  # type: ignore


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Transcribe Engine v1 (Arabic YouTube)")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("video", help="transcribe a single video")
    v.add_argument("url", help="YouTube watch URL")
    v.add_argument("--playlist-url", default="")
    v.add_argument("--keep-audio", action="store_true")
    v.add_argument(
        "--to-parquet", default="", help="also write segments parquet/csv here"
    )

    pl = sub.add_parser("playlist", help="transcribe a whole playlist")
    pl.add_argument("url", help="YouTube playlist URL")
    pl.add_argument("--keep-audio", action="store_true")
    pl.add_argument("--to-parquet", default="")

    for s in (v, pl):
        s.add_argument("--jsonl", default=OUTPUT_JSONL)
        s.add_argument("--db", default=CHECKPOINT_DB)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if os.environ.get("HF_TOKEN"):
        pass  # transcribe_ar picks it up; explicit --hf-token is a v2 item
    if args.cmd == "video":
        rec = process_video(
            args.url,
            playlist_url=args.playlist_url,
            keep_audio=args.keep_audio,
            db_path=args.db,
            jsonl_path=args.jsonl,
        )
        print("done" if rec else "skipped-or-failed")
    else:
        summary = process_playlist(
            args.url, keep_audio=args.keep_audio, db_path=args.db, jsonl_path=args.jsonl
        )
        print(summary)
    if args.to_parquet:
        jsonl_to_parquet_main(args.jsonl, args.to_parquet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
