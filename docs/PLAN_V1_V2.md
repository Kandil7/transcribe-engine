# Transcribe Engine — Plan: v1 (current) and v2 (future)

## Branch strategy

`main` is always green. Every step lands via `feature/*` → `main` with
`git merge --no-ff`, one commit per step. Step branches so far:

- `feature/docs-plan` — this plan + architecture (v1 + v2)
- `feature/schema` — `src/schema.py` JSONL contract + `src/normalize_ar.py`
- `feature/jsonl-parquet` — `src/jsonl_to_parquet.py` + `tests/test_contract.py`
- `feature/pipeline` — `src/youtube.py` + `src/transcribe.py` + `src/pipeline.py`

## v1 — current (locked scope)

Goal: Arabic YouTube → transcription dataset on local RTX 5000.

- Engine: `bakrianoo/cohereX` Python API, model
  `CohereLabs/cohere-transcribe-arabic-07-2026`, `--language ar`,
  `vad_method=silero`, `compute_type=bfloat16`, `batch_size=8`,
  `chunk_size=30`, backend `local`. No diarization.
- Pipeline:
  `yt-dlp metadata → filter → 16kHz mono wav → cohereX VAD+ASR+align
  → QA → videos.jsonl → segments.parquet`
- Outputs:
  - `data/output/videos.jsonl` — one JSON object per video (raw + normalized
    transcript, `segments`, `word_segments`, `align_status`, `playlist_url`,
    `channel`, `license`, `fetched_at`).
  - `data/output/segments.parquet` — one row per segment with
    `playlist_url` + `channel` repeated per row (flat, RAG-ready).
  - `data/output/checkpoint.db` — `video_id, status, attempts, error`.
- Text policy: keep `transcript_raw` (verbatim, ASR training) and
  `transcript_norm` (folded alef/hamza, tatweel stripped, ٠-٩→0-9, RAG).
- Alignment fallback: if no Arabic align model, `align_status=segment_only`
  with empty `word_segments` instead of failing the playlist.
- Audio is ephemeral: deleted after transcription. Store transcript +
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
