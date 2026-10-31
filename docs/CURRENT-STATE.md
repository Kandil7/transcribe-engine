# Transcribe Engine — Current State

Updated: 2026-10-31. `main` is green through `d1e3a69`; a small docs
chore sits uncommitted (stale-count/badge fixes).

## What works right now

- End-to-end GPU run on RTX 5000 (torch 2.11.0+cu128, `float16`):
  17.4-min Arabic video → **112 segments, 2,622 word timestamps,
  `align=ok`**, VAD+ASR in ~44s.
- Resume from checkpoint does zero network for done videos (proven).
- Dataset state on disk: **41 completed videos, 17.5 audio hours** in
  `videos.jsonl`; `segments.parquet` **5,453 rows × 13 cols, 0 nulls**,
  all `align=ok`. Checkpoint db: 41 ok, 1 failed
  (`rx7mm2Ck7Cs`, audio-load error during an interrupted run, retryable).
- 96/96 tests pass, all offline (mocked network/GPU). v1 toolset includes
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

## Playlist run status (paused 2026-10-30)

- Hon checklist against the 57-video playlist: **41 ok / 1 failed /
  15 unattempted**.
- Resuming with the same `cli playlist` command skips the 41 ok videos
  without network and re-attempts the 1 failure; `--to-parquet` should be
  re-run afterwards (or use the converter module directly).

## v2 features wired (2026-10-30)

- **Diarization — GPU-verified** (`--diarize`): default is now
  `nvidia/Nemotron-3-Diarization` (ungated, OpenMDW, 99.2M params —
  beats the pyannote baseline on published DER). Real run on the eval
  clip: 132 turns, 3 speakers, 22s for 650s audio on the RTX 5000.
  Full E2E (`cli video --diarize`): 55 segments annotated, parquet now
  5,453 rows × 14 cols with `speaker` populated. The pyannote path stays
  selectable (`--diarize-model pyannote/...`) but is still gated on HF.
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
- **`--vad-method pyannote`** and **`--backend vllm`** (+ `--vllm-url/
  api-key/args`): pass-through to coherex (which already implements both),
  recorded in `manifest.json`. pyannote VAD is gated behind
  `pyannote/segmentation-3.0` (same acceptance click); vLLM needs the
  `vllm` package on the run box (not installed locally).
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
