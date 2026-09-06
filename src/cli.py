"""CLI for Transcribe Engine v1: single video or playlist → JSONL → Parquet."""

from __future__ import annotations

import argparse

try:
    from .jsonl_to_parquet import main as jsonl_to_parquet_main
    from .pipeline import (
        CHECKPOINT_DB,
        OUTPUT_JSONL,
        process_playlist,
        process_video,
        write_manifest,
    )
    from .transcribe import TranscribeConfig
except ImportError:  # script-style execution
    from jsonl_to_parquet import main as jsonl_to_parquet_main  # type: ignore
    from pipeline import (  # type: ignore
        CHECKPOINT_DB,
        OUTPUT_JSONL,
        process_playlist,
        process_video,
        write_manifest,
    )
    from transcribe import TranscribeConfig  # type: ignore


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
    pl.add_argument(
        "--max-videos",
        type=int,
        default=0,
        help="only take the first N playlist videos (0 = all; for soak tests)",
    )

    for s in (v, pl):
        s.add_argument("--jsonl", default=OUTPUT_JSONL)
        s.add_argument("--db", default=CHECKPOINT_DB)
        s.add_argument(
            "--ffmpeg-location",
            default=None,
            help="ffmpeg binary/dir (default: auto-detect incl. imageio-ffmpeg)",
        )
        s.add_argument("--device", default="cuda", help="torch device (default: cuda)")
        s.add_argument(
            "--compute-type",
            default="float16",
            help="float16 for Turing sm_75; bfloat16 needs Ampere+ (default: float16)",
        )
        s.add_argument("--batch-size", type=int, default=8)
        s.add_argument("--chunk-size", type=float, default=30.0)
        s.add_argument("--retries", type=int, default=3)
        s.add_argument(
            "--hf-token",
            default=None,
            help="HF token for gated models (default: HF_TOKEN env / hf auth login)",
        )
        s.add_argument(
            "--no-align",
            action="store_true",
            help="skip wav2vec2 forced alignment (segment timestamps only)",
        )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = TranscribeConfig(
        device=args.device,
        compute_type=args.compute_type,
        batch_size=args.batch_size,
        chunk_size=args.chunk_size,
        align=not args.no_align,
        hf_token=args.hf_token,
    )
    if args.cmd == "video":
        rec = process_video(
            args.url,
            playlist_url=args.playlist_url,
            keep_audio=args.keep_audio,
            retries=args.retries,
            db_path=args.db,
            jsonl_path=args.jsonl,
            ffmpeg_location=args.ffmpeg_location,
            config=config,
        )
        print("done" if rec else "skipped-or-failed")
        from pathlib import Path

        write_manifest(
            str(Path(args.jsonl).parent / "manifest.json"),
            {
                "mode": "video",
                "url": args.url,
                "video_id": rec.video_id if rec else "",
                "ok": rec is not None,
            },
            config,
        )
    else:
        summary = process_playlist(
            args.url,
            keep_audio=args.keep_audio,
            db_path=args.db,
            jsonl_path=args.jsonl,
            ffmpeg_location=args.ffmpeg_location,
            config=config,
            max_videos=args.max_videos,
        )
        print(summary)
    if args.to_parquet:
        jsonl_to_parquet_main(args.jsonl, args.to_parquet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
