# Transcribe Engine — Plan: v1 (current) and v2 (future)

## Branch strategy

`main` is always green. Every step lands via `feature/*` → `main` with
`git merge --no-ff`, one commit per step. Step branches so far:

- `feature/docs-plan` — this plan + architecture (v1 + v2)
- `feature/schema` — `src/schema.py` JSONL contract + `src/normalize_ar.py`
- `feature/jsonl-parquet` — `src/jsonl_to_parquet.py` + `tests/test_contract.py`
- `feature/pipeline` — `src/youtube.py` + `src/transcribe.py` + `src/pipeline.py`
- `feature/cli` — `src/cli.py`, HF token wiring, resume skip, usage docs
- `feature/gpu-run-fixes` *(unmerged work in tree)* — ffmpeg shim, `noplaylist`
  guard, audio reuse + ownership, `float16` default, OOM fallback, VRAM release
- `feature/full-fixes` *(unmerged work in tree)* — `TranscribeSession`,
  `qa.py`, JSONL upsert, manifest, prefetch, CLI knobs, mocked test suites

## v1 — current (locked scope, implemented + proven on GPU)

Goal: Arabic YouTube → transcription dataset on local RTX 5000.

- Engine: `bakrianoo/cohereX` Python API, model
  `CohereLabs/cohere-transcribe-arabic-07-2026`, `--language ar`,
  `vad_method=silero`, `compute_type=float16` (Turing sm_75 has no bf16
  units), `batch_size=8` (→4 on OOM), `chunk_size=30`, backend `local`.
  No diarization.
- Pipeline:
  `yt-dlp metadata → 16kHz mono wav (reuse validated by duration) →
  TranscribeSession VAD+ASR+align → QA flags → videos.jsonl (upsert) →
  segments.parquet`, with per-run `manifest.json` provenance.
- Playlist runs keep one resident model and prefetch the next audio
  during GPU transcription; single-video URLs must be bare `watch?v=`
  links (`noplaylist` backstop in code).
- Outputs:
  - `data/output/videos.jsonl` — one JSON object per video (raw + normalized
    transcript, `segments`, `word_segments`, `align_status`, `playlist_url`,
    `channel`, `license`, `qa`, `timings`, `norm_version`, `fetched_at`).
  - `data/output/segments.parquet` — one row per segment with
    `playlist_url` + `channel` repeated per row (flat, RAG-ready).
  - `data/output/checkpoint.db` — `video_id, status, attempts, error`.
  - `data/output/manifest.json` — model, device, git sha, counts.
- Text policy: keep `transcript_raw` (verbatim, ASR training) and
  `transcript_norm` (folded alef/hamza, tatweel stripped, ٠-٩→0-9, RAG).
- Alignment fallback: if no Arabic align model, `align_status=segment_only`
  with empty `word_segments` instead of failing the playlist.
  `--no-align` records `skipped` for fast drafts.
- Audio is ephemeral: only attempt-owned wavs are deleted after
  transcription (reused cache is never deleted). Store transcript +
  metadata only (YouTube ToS / copyright).

## v2 — future (not started)

- Speaker diarization via `pyannote/speaker-diarization-community-1`
  (`exclusive_speaker_diarization` reconciled to word timestamps).
- `vad_method=pyannote` option; vLLM backend for throughput.
- Language auto-detect (`coherex[langid]`) with explicit-`ar` default.
- `segments.parquet` gains `speaker` column; JSONL gains `speakers`.
- Dialect tag + per-video QA scores (empty-ratio, LID confidence,
  mean word score); 1–2h hand-transcribed WER/CER eval set.
- Streamlit viewer; Dockerfile (CUDA + ffmpeg + uv); Colab notebook.
