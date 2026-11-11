"""CLI for Transcribe Engine v1: single video or playlist → JSONL → Parquet."""

from __future__ import annotations

import argparse

from .jsonl_to_parquet import main as jsonl_to_parquet_main
from .models import DIALECT_MODEL, DIARIZE_MODEL, LID_MODEL
from .pipeline import (
    CHECKPOINT_DB,
    OUTPUT_JSONL,
    process_playlist,
    process_video,
    write_manifest,
)
from .transcribe import TranscribeConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Transcribe Engine v1 (Arabic YouTube)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "make-ref",
        help="segment-aligned WER reference template (forward all args after it)",
    ).add_argument(
        "tool_args", nargs=argparse.REMAINDER, help="arguments passed to make_reference"
    )
    sub.add_parser(
        "score",
        help="WER/CER vs hand reference (forward all args after it)",
    ).add_argument(
        "tool_args", nargs=argparse.REMAINDER, help="arguments passed to score_wer"
    )

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

    pf = sub.add_parser(
        "prefetch", help="load/verify all pipeline models on local disk"
    )
    pf.add_argument(
        "--device",
        default="cpu",
        help="device for the verification load (default: cpu — cache check, no GPU juggling)",
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
            "--language",
            default="ar",
            help="explicit language code for Cohere Transcribe (default: ar; no LID)",
        )
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
        s.add_argument(
            "--vad-method",
            default="silero",
            choices=["silero"],
            help="VAD backend (silero only — the pyannote option was removed "
            "with its gated model, ADR 18)",
        )
        s.add_argument(
            "--backend",
            default="local",
            choices=["local", "vllm"],
            help="ASR backend: in-process local, or vLLM server (needs vllm installed)",
        )
        s.add_argument(
            "--vllm-url",
            default="",
            help="running vLLM server URL (empty: coherex starts/stops its own)",
        )
        s.add_argument("--vllm-api-key", default=None, help="vLLM server API key")
        s.add_argument(
            "--vllm-args",
            default="",
            help="extra `vllm serve` args when coherex launches its own server",
        )
        s.add_argument(
            "--diarize",
            action="store_true",
            help="Nemotron-3 speaker diarization: adds speaker to segments/words",
        )
        s.add_argument(
            "--diarize-model",
            default=DIARIZE_MODEL,
            help="HF repo id of the Nemotron-3 diarization model",
        )
        s.add_argument(
            "--lid",
            action="store_true",
            help="audio language ID (mms-lid-1024): records lid_lang/"
            "lid_confidence; QA flags lid_mismatch (CC-BY-NC model)",
        )
        s.add_argument(
            "--lid-model",
            default=LID_MODEL,
            help="HF repo id of the LID model",
        )
        s.add_argument(
            "--dialect",
            action="store_true",
            help="written-dialect tag (MARBERTv2): records dialect/"
            "dialect_confidence (MAGHREB|LEV|MSA|GLF|EGY)",
        )
        s.add_argument(
            "--dialect-model",
            default=DIALECT_MODEL,
            help="HF repo id of the dialect classifier",
        )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "prefetch":
        from .prefetch import prefetch_models

        results = prefetch_models(device=args.device)
        for name, status in results.items():
            print(f"{name}: {status}")
        return 0
    if args.cmd == "score":
        # forwarded raw: everything after `score`
        from .score_wer import main as score_main

        score_main(args.tool_args)
        return 0
    if args.cmd == "make-ref":
        from .make_reference import main as make_ref_main

        make_ref_main(args.tool_args)
        return 0
    config = TranscribeConfig(
        device=args.device,
        compute_type=args.compute_type,
        vad_method=args.vad_method,
        batch_size=args.batch_size,
        chunk_size=args.chunk_size,
        align=not args.no_align,
        hf_token=args.hf_token,
        language=args.language,
        backend=args.backend,
        vllm_url=args.vllm_url,
        vllm_api_key=args.vllm_api_key,
        vllm_args=args.vllm_args,
        diarize=args.diarize,
        diarize_model=args.diarize_model,
        lid=args.lid,
        lid_model=args.lid_model,
        dialect=args.dialect,
        dialect_model=args.dialect_model,
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
