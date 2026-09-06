# Transcribe Engine — Architecture (v1)

```
YouTube URL / playlist
  → youtube.py (metadata, playlist expand, 16kHz wav download)
  → transcribe.py (cohereX: VAD silero → Cohere-AR ASR → wav2vec2 align)
  → normalize_ar.py (raw vs normalized Arabic text)
  → pipeline.py (checkpoint SQLite, retry, logging, JSONL append)
  → videos.jsonl → jsonl_to_parquet.py → segments.parquet
```

## Module responsibilities

- `src/schema.py` — JSONL contract: `VideoRecord` with `playlist_url`,
  `channel`, `align_status`, `transcript_raw/norm`, `segments`,
  `word_segments`. Idempotent on `video_id`.
- `src/youtube.py` — yt-dlp wrappers. Playlist expansion uses
  `entry['id'] → watch URL`, skips `None`/private. Single `extract_info`
  + `prepare_filename` for the wav path. Handles `tags=None`,
  `thumbnails[]` list, `duration=None`. 1–2s delay between videos.
- `src/transcribe.py` — `bakrianoo/cohereX` Python API only (no CLI
  subprocess): `load_model` → `transcribe(language="ar")` →
  `load_align_model("ar")` → `align`. Falls back to segment-only.
- `src/normalize_ar.py` — pure-stdlib Arabic fold for `transcript_norm`.
- `src/pipeline.py` — per-video orchestration, SQLite checkpoint,
  exponential retry, stdlib `logging`.
- `src/jsonl_to_parquet.py` — flatten JSONL segments → Parquet via
  polars (pandas fallback, csv last resort). Words stay in JSONL.

## VRAM budget (RTX 5000 16GB, sm_75)

2B ASR fp16 (~4GB) + aligner (~2GB), run sequentially, never
concurrent. `batch_size=8`, drop to 4 on OOM. Diarization (v2) adds
~2GB and runs as its own sequential stage.
