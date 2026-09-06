# Transcribe Engine

Arabic YouTube transcription data engine built on `bakrianoo/cohereX`
(Cohere `cohere-transcribe-arabic-07-2026` + VAD + forced alignment).

Branch strategy: `main` + `feature/*` per step, merge with `--no-ff`.
Every step is a separate commit. See `docs/PLAN_V1_V2.md`.

## v1 scope (locked)

- Local WSL / RTX 5000, transcript-only (no diarization)
- `videos.jsonl` (per video) → `segments.parquet` (per segment, with `playlist_url` + `channel`)
- Pipeline: yt-dlp metadata → 16kHz wav → cohereX (`ar`, `silero`, `bf16`) → QA → JSONL → Parquet

## Setup (GPU machine)

```bash
pip install -e ".[engine]"   # coherex, yt-dlp, pydantic, polars
# ffmpeg must be on PATH; then accept gated models and log in:
hf auth login
```

Gated models: `CohereLabs/cohere-transcribe-arabic-07-2026`
(+ `pyannote/speaker-diarization-community-1` only for v2).
`HF_TOKEN` env is honored if set, otherwise uses `hf auth login`.

## Usage

```bash
# single video (+ parquet in one go)
python -m src.cli video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --playlist-url "https://youtube.com/playlist?list=PLxxx" \
  --to-parquet data/output/segments.parquet

# playlist (checkpointed, resumable)
python -m src.cli playlist "https://www.youtube.com/playlist?list=PLxxx" \
  --to-parquet data/output/segments.parquet
```

## Outputs

- `data/output/videos.jsonl` — one JSON object per video
- `data/output/segments.parquet` (or `.csv` fallback without polars/pandas)
- `data/output/checkpoint.db` — resume state; `playlist_summary.json`
