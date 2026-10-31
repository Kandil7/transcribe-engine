# Transcribe Engine — Current State

Updated: 2026-10-31. `main` is green through `d1e3a69`; a small docs
chore sits uncommitted (stale-count/badge fixes).

## What works right now

- End-to-end GPU run on RTX 5000 (torch 2.11.0+cu128, `float16`):
  17.4-min Arabic video → **112 segments, 2,622 word timestamps,
  `align=ok`**, VAD+ASR in ~44s.
- Resume from checkpoint does zero network for done videos (proven).
- **Full playlist complete (2026-10-31): 57/57 ok, 0 failed.** Corpus:
  **57 videos, 35.7 audio hours, 10,836 segments × 14 cols (0 nulls),
  297,037 word timestamps**, QA: 56 clean + 1 `align_segment_only`
  (memory-pressure casualty, re-alignable), dialect `EGY` × 57.
- 97/97 tests pass, all offline (mocked network/GPU). v1 toolset includes
  `src/score_wer.py` WER scorer, `src/viewer.py` Streamlit viewer, and
  `qa_scores` numeric metrics (backfilled across all 41 records:
  mean_word_score 0.571–0.743 (mean 0.633), speech_ratio 0.91–0.97,
  repeat_max ≤ 31 = genuine lazy intros, arabic_ratio 1.000 corpus-wide).
- Repeat-artifact investigation closed: no decoder loops, all repeated
  passages are genuine teacher rhetoric (`docs/experiments/
  repeat-artifact-resolution.md`).
- Code intelligence: structural graph (258n/731e), graphify (143n, 10
  communities), repomix pack, code-review-graph all built; see
  `docs/CODEBASE-INTELLIGENCE.md`.

## Numbers to beat

| Metric | Value |
|---|---|
| VAD+ASR, 1041s audio, batch 8, fp16 | ~44s wall |
| Aligner download (one-time, ~1.2GB, throttled link) | ~15 min |
| Model load from HF cache (4.1GB) | ~2s |
| ASR resident | ~4GB VRAM; +aligner ~6GB in playlist sessions |
| Corpus so far (41 videos) | 17.5h audio, 5,453 segments, ~55k words |

## Playlist run status — COMPLETE (2026-10-31)

- **57/57 ok, 0 failed** (1,648s elapsed for the final 10; earlier
  partial runs contributed the first 47). Parquet rebuilt at run end.
- Memory lesson: the 100+ min videos (200MB+ wavs) need ~800MB transient
  for coherex's whole-file audio load; under commit pressure they
  failed / degraded to `align=segment_only` / hung a reader thread. With
  headroom freed (Docker stopped, hung process killed) the same videos
  completed clean with full alignment. Documented in ADR 17.

## v2 features wired (2026-10-30)

- **Diarization — GPU-verified** (`--diarize`): `nvidia/Nemotron-3-Diarization`
  (ungated, OpenMDW, 99.2M params — beats the pyannote baseline on
  published DER) is the **sole backend since ADR 18** (pyannote path
  removed with its gated models). Real run on the eval clip: 132 turns,
  3 speakers, 22s for 650s audio on the RTX 5000.
  Full E2E (`cli video --diarize`): 55 segments annotated, parquet now
  10,836 rows × 14 cols with `speaker` populated where requested.
  Audio decoding goes through the ffmpeg CLI shim (torchcodec needs
  shared-FFmpeg DLLs this box doesn't have).
- **HF cache-root resolver** (`resolve_cache_dir` in `src/transcribe.py`):
  this machine's caches are split across two roots; a hub upgrade made
  the hub re-download the 4.13GB ASR weights that existed in the other
  root, failing on disk space. The resolver picks the root that actually
  holds the model (by content, not folder presence) and is wired into
  every model load. Also freed 1.55GB of stale partial downloads.
- **Local-first loading + `cli prefetch`**: every model load is
  cache-only before any network (`load_local_first`); `python -m src.cli
  prefetch` verifies all 4 models (ASR, aligner, Nemotron, LID) in one
  process each — **verified `local` × 4** on this box with zero
  downloads. Process isolation exists because freed multi-GB weights
  don't reliably return Windows commit in-process (the LID load failed
  sequentially even though it fits alone).
- **`--backend vllm`** (+ `--vllm-url/api-key/args`): pass-through to
  coherex, recorded in `manifest.json`; needs the `vllm` package on the
  run box (not installed locally). **pyannote VAD removed** (ADR 18):
  silero is the only VAD, Nemotron-3 covers the speaker side.
- **`--language`**: explicit language code pass-through (default `ar`),
  engine-reported language now recorded on each `VideoRecord`. True
  auto-detect is impossible in coherex (it raises on `language=None`).
- **Written-dialect tag** (`--dialect`): `src/dialect.py` on MARBERTv2
  (`IbrahimAmin/marbertv2-arabic-written-dialect-classifier`, labels
  `MAGHREB|LEV|MSA|GLF|EGY`). Classifies transcript text (no audio
  needed), averages softmax over spread windows, records
  `dialect`/`dialect_confidence` as metadata (never QA-flags).
  **Verified on all 41 transcripts: EGY × 41, confidence mean 0.979**.
- **Audio LID** (`--lid`): `src/lid.py` on `facebook/mms-lid-1024`
  (1B params, CC-BY-NC — flagged in docs). Transient per-video load,
  scores a 30s middle clip, records `lid_lang`/`lid_confidence`, QA
  flags `lid_mismatch` via an ISO 639-1→639-3 map. **GPU + E2E
  verified**: standalone `ara` @ 0.998 on the eval clip; CLI run also
  proved the memory-recovery chain (the 1B model's 2.5GB mmap hits
  Windows commit limits next to resident ASR — the session frees
  finished models and retries; `lid_failed` flag if all retries fail).
- **Deployment**: `Dockerfile` (CUDA 12.8 + torch cu128 + ffmpeg, CLI
  entrypoint) + `.dockerignore` + `notebooks/transcribe-engine-colab.ipynb`
  (T4 = same sm_75; 8 cells, GPU check → install → token → run → inspect
  → Drive persistence). **Docker image built and smoke-tested**
  (`docker run --rm transcribe-engine --help` verified).
- **Corpus overlap** (`docs/experiments/series-overlap.md`): found one
  re-upload pair (`i41KPdjG0O8` ↔ `R0tJASk3fLw`, Jaccard 0.92) — dedup at
  dataset-build time, not in the pipeline.

## Known limitations

- **Playlist run in progress** (resumed 2026-10-31): 41 ok / 1 retry /
  15 unattempted; parquet rebuilds at the run's end.
- YouTube throttling on this link (~0.3–1 MB/s): audio re-downloads and
  model fetches are slow but resumable.
- LICENSE: Apache-2.0 added (2026-10-31); swap before public push if a
  different license is wanted.
- WER: cross-ASR agreement measured
  (`docs/experiments/cross-asr-agreement.md`, CER disagreement 0.532
  between Whisper-large-v3-turbo and the pipeline). The gold-standard
  hand reference remains pending user correction
  (`docs/experiments/wer-eval-protocol.md`).
