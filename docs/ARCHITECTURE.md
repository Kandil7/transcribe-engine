# Transcribe Engine — Architecture (v1)

```
YouTube URL / playlist
  → youtube.py (metadata, playlist expand, 16kHz wav download, noplaylist guard)
  → transcribe.py (TranscribeSession: VAD silero → Cohere-AR ASR → wav2vec2 align)
  → normalize_ar.py (raw vs normalized Arabic text, versioned)
  → qa.py (per-video QA flags) → pipeline.py (checkpoint, retry, upsert, manifest)
  → videos.jsonl → jsonl_to_parquet.py → segments.parquet
```

## Module responsibilities

- `src/schema.py` — JSONL contract: `VideoRecord` with `playlist_url`,
  `channel`, `license`, `align_status` (`ok | segment_only | skipped`),
  `transcript_raw/norm` + `norm_version`, `qa` flags, `timings`,
  `segments`, `word_segments`. Idempotent on `video_id`.
- `src/youtube.py` — yt-dlp wrappers. `noplaylist=True` everywhere a
  single video is expected (watch URLs carrying `&list=` must never
  expand). Playlist expansion uses `entry['id'] → watch URL`, skips
  `None`/private. Audio reuse validated by wav duration vs metadata.
  Handles `tags=None`, `thumbnails[]` list, `duration=None`.
  1–2s delay between videos.
- `src/transcribe.py` — `bakrianoo/cohereX` Python API only (no CLI
  subprocess). `TranscribeSession` keeps ASR + aligner resident across
  videos (playlist pays the weight load once); `transcribe_ar` is the
  single-shot wrapper. Falls back to segment-only (logs the cause);
  `--no-align` records `skipped`. `ensure_ffmpeg_on_path` shims a
  `ffmpeg.exe` for coherex subprocess calls (imageio-ffmpeg hosts).
- `src/normalize_ar.py` — pure-stdlib Arabic fold for `transcript_norm`,
  stamped with `NORM_VERSION`.
- `src/qa.py` — stdlib QA gates (`empty_transcript`, `no_segments`,
  `no_words`, `align_*`, `duration_mismatch`, `bad_timestamps`,
  `short_audio`). Flags never drop records; filter `qa == []` downstream.
- `src/pipeline.py` — per-video orchestration, SQLite checkpoint,
  exponential retry, JSONL upsert, per-video timings, `manifest.json`
  provenance, next-audio prefetch overlap, stdlib `logging` with
  tracebacks.
- `src/jsonl_to_parquet.py` — flatten JSONL segments → Parquet via
  polars (pandas fallback, csv last resort). Rows coerced to the column
  contract; missing input yields an empty table. Words stay in JSONL.

## VRAM budget (RTX 5000 16GB, sm_75)

`float16` (Turing has no bf16 tensor cores; coherex `default` = bf16).
Single video: 2B ASR fp16 (~4GB), released before the aligner (~2GB)
loads. Playlist session: both resident (~6GB, needs ~7GB free).
`batch_size=8`, drop to 4 on OOM. Diarization (v2) adds ~2GB and runs
as its own sequential stage.
