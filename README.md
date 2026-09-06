# Transcribe Engine

Arabic YouTube transcription data engine built on `bakrianoo/cohereX`
(Cohere `cohere-transcribe-arabic-07-2026` + VAD + forced alignment).

Branch strategy: `main` + `feature/*` per step, merge with `--no-ff`.
Every step is a separate commit. See `docs/PLAN_V1_V2.md`.

## v1 scope (locked)

- Local WSL / RTX 5000, transcript-only (no diarization)
- `videos.jsonl` (per video) → `segments.parquet` (per segment, with `playlist_url` + `channel`)
- Pipeline: yt-dlp metadata → 16kHz wav → cohereX (`ar`, `silero`, `bf16`) → QA → JSONL → Parquet
