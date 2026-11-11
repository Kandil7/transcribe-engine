# Transcribe Engine — Architecture (v1 + v2)

```
YouTube URL / playlist
  → youtube.py (metadata, playlist expand, 16kHz wav download, noplaylist guard)
  → transcribe.py (TranscribeSession:
        VAD silero → Cohere-AR ASR → wav2vec2 align
        → diarize.py (optional Nemotron-3 speakers)
        → lid.py (optional audio language ID)
        → dialect.py (optional written-dialect tag))
  → normalize_ar.py (raw vs normalized Arabic text, versioned)
  → qa.py (QA flags + numeric scores) → pipeline.py (checkpoint, retry,
        upsert, manifest, prefetch, timings)
  → videos.jsonl → jsonl_to_parquet.py → segments.parquet
```

Shared infrastructure (ADR 19): `models.py` is the single source of
truth for every model repo id; `hub.py` owns HF loading (cache resolver,
local-first, offline context, token); `audio_io.py` owns the ffmpeg shim
and waveform decoding; `store.py` is the one videos.jsonl reader used by
all consumers.

Tooling around the pipeline: `score_wer.py` and `make_reference.py`
(also reachable as `cli score` / `cli make-ref`),
`viewer.py` (Streamlit dataset browser + segment audio playback),
`prefetch.py` (verify all models on local disk).

## Module responsibilities

- `src/schema.py` — JSONL contract: `VideoRecord` with `playlist_url`,
  `channel`, `license`, `align_status` (`ok | segment_only | skipped`),
  `transcript_raw/norm` + `norm_version`, `qa` flags, `qa_scores`
  (`mean_word_score`, `speech_ratio`, `empty_ratio`, `repeat_max`,
  `arabic_ratio`), `diarize_status` + `speakers`, `lid_status` +
  `lid_lang/confidence`, `dialect_status` + `dialect/confidence`,
  `timings`, `segments` (+ optional `speaker`), `word_segments` (+
  optional `speaker`). Idempotent on `video_id`; old lines parse
  (missing fields backfill defaults).
- `src/youtube.py` — yt-dlp wrappers. `noplaylist=True` everywhere a
  single video is expected (watch URLs carrying `&list=` must never
  expand). Playlist expansion uses `entry['id'] → watch URL`, skips
  `None`/private. Audio reuse validated by wav duration vs metadata.
  `video_id_from_url` is the single id authority. 1–2s delay between
  videos. Owned-audio deletion semantics (cached wavs never deleted).
- `src/transcribe.py` — `bakrianoo/cohereX` Python API only (no CLI
  subprocess). `TranscribeSession` keeps ASR + aligner resident across
  videos (playlist pays the weight load once); `transcribe_ar` is the
  single-shot wrapper. Annotation stages run through `_stage`, the
  never-fail wrapper whose success paths live in `_do_diarize` /
  `_do_lid` / `_do_dialect`; `_STAGE_RESET` owns each stage's failure
  keys. Options: `--vad-method` (silero), `--backend`
  (`local | vllm` pass-through), `--diarize`, `--lid`, `--dialect`,
  `--no-align`. Never-fail stages: a failing optional stage records its
  status and a QA flag, the run continues. The session→pipeline result
  contract is `schema.EngineResult` (TypedDict).
- `src/hub.py` — model-loading infrastructure (ADR 13/15):
  `resolve_cache_dir` (picks the HF cache root that actually holds a
  model — this machine's caches are split across two roots),
  `load_local_first` (cache-only attempt before any network),
  `local_only` (HF_HUB_OFFLINE context), `resolve_token`.
- `src/models.py` — model repo ids; the single source of truth
  (engine config, CLI defaults, prefetch loaders all reference it).
- `src/audio_io.py` — `ensure_ffmpeg_on_path` (the coherex shim) and
  `load_audio_16k` (ffmpeg CLI decoding; lid and diarize both consume
  it, no feature-to-feature imports).
- `src/diarize.py` — Nemotron-3 speaker diarization (sole backend since
  ADR 18; pyannote removed). Arrival-ordered channels → `SPEAKER_00..`;
  `assign_speakers` maps turns onto segments/words by max time overlap
  (pure, tested). Audio decoding via the ffmpeg CLI shim (torchcodec
  needs shared-FFmpeg DLLs this box lacks).
- `src/lid.py` — audio language ID on `facebook/mms-lid-1024`
  (CC-BY-NC; scores a 30s middle clip; ISO 639-3 output).
- `src/dialect.py` — written-dialect tag on MARBERTv2
  (`MAGHREB|LEV|MSA|GLF|EGY`); softmax averaged over spread text
  windows (model caps at 512 tokens). Metadata only, never QA-flags.
- `src/normalize_ar.py` — pure-stdlib Arabic fold for `transcript_norm`,
  stamped with `NORM_VERSION`.
- `src/qa.py` — stdlib QA gates (`empty_transcript`, `no_segments`,
  `no_words`, `align_*`, `diarize_failed`, `lid_failed`, `lid_mismatch`,
  `duration_mismatch`, `bad_timestamps`, `short_audio`) plus numeric
  `qa_scores`. Flags never drop records; filter `qa == []` downstream.
- `src/pipeline.py` — per-video orchestration, SQLite checkpoint,
  exponential retry, JSONL upsert, per-video timings, `manifest.json`
  provenance (model/device/compute/vad/backend/language/diarize/git
  sha), next-audio prefetch overlap, stdlib `logging` with tracebacks.
- `src/jsonl_to_parquet.py` — flatten JSONL segments → Parquet via
  polars (pandas fallback, csv last resort). Rows coerced to
  `PARQUET_COLUMNS` (14 incl. `speaker`); missing input yields an empty
  table. Words stay in JSONL.
- `src/store.py` — the one videos.jsonl reader: `load_records`
  (tolerant, empty list on missing file) and `load_video` (strict,
  SystemExit on missing file/id). Used by viewer, score_wer and
  make_reference — replacing three divergent copies.
- `src/prefetch.py` — `cli prefetch`: loads every pipeline model
  local-first in one subprocess per model (process isolation: freed
  multi-GB weights don't return Windows commit reliably in-process).
  Reports `local` vs `downloaded` per model.
- `src/score_wer.py` — WER/CER vs a hand reference (word-DP, both sides
  normalized). Understands `[start-end]` line timestamps and reports
  per-segment WER with the worst lines. `--slice A-B` scores a window.
- `src/make_reference.py` — builds the segment-aligned correction
  template from YouTube auto-caption per-word timestamps (one
  `[start-end]` line per pipeline segment).
- `src/viewer.py` — Streamlit dataset browser: per-video chips (qa,
  align, lid, dialect, word score), segment table with click-to-play
  audio windows; doubles as the WER correction aid. Pure helpers tested.

## VRAM & memory budget (RTX 5000 16GB, sm_75)

`float16` (Turing has no bf16 tensor cores; coherex `default` = bf16).
- ASR (Cohere-AR, 2B) fp16 ~4GB + aligner ~2GB: ~6GB resident in a
  playlist session, needs ~7GB free. `batch_size=8`, drop to 4 on OOM.
- Nemotron-3 diarization ~400MB, transient per video. MMS-LID 1B
  (~2.5GB mmap) loads transiently and can hit **Windows commit limits**
  next to resident ASR — the session frees finished models and retries
  (ADR 14). MARBERTv2 dialect ~500MB, transient.
- **Long videos need commit headroom** (ADR 17): 100+ min videos load
  ~800MB wav transients inside coherex; check free commit before big
  batches rather than trusting retries. On failure the run degrades
  (`align=segment_only`, QA-flagged) and continues — never-fail.

## Model loading (ADR 13/15)

Every model load is local-first: `hub.load_local_first` attempts the load
cache-only and only goes online on a genuine cache miss. Models resolve
their cache root via `hub.resolve_cache_dir` (handles split HF cache
roots). `cli prefetch` verifies the full set on disk. Runs are
offline-capable once prefetch reports `local`.
