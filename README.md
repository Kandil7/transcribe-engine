# Transcribe Engine

[![Python ≥3.10](https://img.shields.io/badge/python-%3E%3D3.10-blue)](pyproject.toml)
[![PyTorch cu128](https://img.shields.io/badge/torch-2.11%2Bcu128-orange)](https://pytorch.org/)
[![GPU](https://img.shields.io/badge/GPU-RTX%205000%20sm__75-76B900)](docs/ARCHITECTURE.md#vram-budget-rtx-5000-16gb-sm_75)
[![Arabic ASR](https://img.shields.io/badge/arabic-ASR-green)](https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026)
[![Tests](https://img.shields.io/badge/tests-97%20passing-brightgreen)](tests/)
[![Scope](https://img.shields.io/badge/v1%2Bv2-optional%20diarize%2FLID-lightgrey)](docs/PLAN_V1_V2.md)
[![Code Intelligence](https://img.shields.io/badge/🧠_Code_Graph-docs-blue)](docs/CODEBASE-INTELLIGENCE.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Arabic YouTube → transcription dataset engine built on `bakrianoo/cohereX`:
Cohere `cohere-transcribe-arabic-07-2026` ASR + Silero VAD + wav2vec2
forced alignment, running locally on an RTX 5000.

Proven run: a 17.4-minute Arabic video → **112 segments, 2,622 word
timestamps, `align=ok`** in under a minute of GPU time (see
`docs/CURRENT-STATE.md`).

## How it works

```text
YouTube URL / playlist
  → youtube.py      metadata + 16kHz mono wav (noplaylist guard, reuse validated by duration)
  → transcribe.py   TranscribeSession: Silero VAD → Cohere-AR ASR (fp16, cuda) → wav2vec2 align
  → normalize_ar.py raw vs normalized Arabic text (versioned fold)
  → qa.py           per-video QA flags (never drops records)
  → pipeline.py     SQLite checkpoint, retry, JSONL upsert, timings, manifest, audio prefetch
  → videos.jsonl → jsonl_to_parquet.py → segments.parquet (flat, RAG-ready)
```

Single videos load the model once; playlists keep **one resident model**
for all videos and prefetch the next audio while the GPU transcribes.
Every model load is **local-first**: cache-only before any network, so
runs are offline-capable once `prefetch` reports `local`.

## Setup (GPU machine)

```bash
pip install -e ".[engine]"   # coherex, yt-dlp, polars
pip install -e ".[viewer]"   # streamlit (dataset viewer)
pip install -e ".[test]"     # pytest
# ffmpeg: system install preferred; otherwise imageio-ffmpeg is auto-shimmed
# to data/bin/ffmpeg.exe on first run (coherex shells out to `ffmpeg`).
# Accept the gated model, then log in:
hf auth login
```

Gated model: [`CohereLabs/cohere-transcribe-arabic-07-2026`](https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026)
(the only gated model — diarization runs ungated Nemotron-3).
`--hf-token` wins if passed, else `HF_TOKEN` env, else `hf auth login`.

> Windows consoles default to cp1252 and crash printing Arabic: set
> `PYTHONUTF8=1` (or run under `chcp 65001`) before transcribing.

## Usage

```bash
# one-time: verify every model is on local disk (downloads only what's missing)
python -m src.cli prefetch

# single video (+ parquet in one go). Use a BARE watch URL —
# strip &list=/&index= params (yt-dlp treats them as a playlist).
python -m src.cli video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --playlist-url "https://youtube.com/playlist?list=PLxxx" \
  --to-parquet data/output/segments.parquet

# playlist (checkpointed, resumable)
python -m src.cli playlist "https://www.youtube.com/playlist?list=PLxxx" \
  --to-parquet data/output/segments.parquet

# skip alignment for a fast draft (segment timestamps only)
python -m src.cli video "https://www.youtube.com/watch?v=VIDEO_ID" --no-align \
  --to-parquet data/output/segments.parquet
```

### All flags (`video` and `playlist`)

| Flag | Default | Meaning |
|---|---|---|
| `--playlist-url` (video only) | `""` | Recorded per row for RAG provenance |
| `--keep-audio` | off | Keep 16kHz wavs (default: ephemeral, deleted after use) |
| `--to-parquet` | `""` | Also flatten JSONL → parquet/csv here |
| `--jsonl` / `--db` | `data/output/...` | Override output paths |
| `--ffmpeg-location` | auto | ffmpeg binary/dir (env → imageio-ffmpeg → PATH) |
| `--device` | `cuda` | Torch device (`cuda` / `cpu`) |
| `--compute-type` | `float16` | `float16` on Turing sm_75; `bfloat16` needs Ampere+ |
| `--batch-size` | `8` | VAD chunks per forward pass (auto-drops to 4 on OOM) |
| `--chunk-size` | `30.0` | Max VAD-merged seconds per chunk (model hard limit: 35) |
| `--retries` | `3` | Per-video attempts, exponential backoff |
| `--language` | `ar` | Explicit language code (Cohere Transcribe has no LID) |
| `--max-videos` (playlist) | `0` = all | Only take the first N videos (soak tests) |
| `--hf-token` | env/login | Token for gated models |
| `--no-align` | off | Skip wav2vec2 alignment (`align_status=skipped`) |
| `--vad-method` | `silero` | VAD backend (silero only — pyannote option removed, ADR 18) |
| `--backend` | `local` | `vllm` offloads ASR to a vLLM server (needs `vllm` installed) |
| `--vllm-url` / `--vllm-api-key` / `--vllm-args` | `""` | vLLM server endpoint, key, and extra `vllm serve` args (coherex starts its own server when URL is empty) |
| `--diarize` | off | Nemotron-3 speaker diarization (ungated, OpenMDW): adds `speaker` to segments/words |
| `--diarize-model` | Nemotron-3 | HF repo id of the Nemotron-3 diarization model |
| `--lid` | off | Audio language ID: records `lid_lang`/`lid_confidence`, QA flags `lid_mismatch` (model is CC-BY-NC) |
| `--lid-model` | `facebook/mms-lid-1024` | HF repo id of the LID model |
| `--dialect` | off | Written-dialect tag (MARBERTv2): records `dialect`/`dialect_confidence` (`MAGHREB`\|`LEV`\|`MSA`\|`GLF`\|`EGY`) |
| `--dialect-model` | marbertv2-dialect | HF repo id of the dialect classifier |

## Outputs

| Path | Content |
|---|---|
| `data/output/videos.jsonl` | One JSON object per video (upserted on `video_id`) |
| `data/output/segments.parquet` | One row per segment (`.csv` fallback without polars/pandas) |
| `data/output/checkpoint.db` | Resume state: `video_id, status, attempts, error` |
| `data/output/playlist_summary.json` | `{total, ok, failed}` per playlist run |
| `data/output/manifest.json` | Run provenance: model, device, git sha, counts |

### `videos.jsonl` record fields

`video_id`, `video_title`, `channel`, `channel_id`, `upload_date`,
`license`, `playlist_url`, `source_url`, `duration`, `language`,
`model`, `align_status` (`ok` \| `segment_only` \| `skipped`),
`transcript_raw`, `transcript_norm`, `norm_version`, `qa` (flags, `[]` =
clean), `qa_scores` (numeric: `mean_word_score`, `speech_ratio`,
`empty_ratio`, `repeat_max`, `arabic_ratio`), `diarize_status` (`ok` \| `failed` \| `""`),
`speakers` (Nemotron-3 speaker labels), `lid_status` (`ok` \| `failed` \| `""`),
`lid_lang` (ISO 639-3), `lid_confidence`, `dialect_status` (`ok` \| `failed` \| `""`),
`dialect` (`MAGHREB` \| `LEV` \| `MSA` \| `GLF` \| `EGY`), `dialect_confidence`,
`timings` (`download/transcribe/total_seconds`),
`segments` (`start/end/text/words` + optional `speaker`), `word_segments`
(`word/start/end/score` + optional `speaker`), `fetched_at`.

### `segments.parquet` columns

`video_id`, `video_title`, `channel`, `channel_id`, `upload_date`,
`playlist_url`, `start`, `end`, `text_raw`, `text_norm`, `word_count`,
`align_status`, `speaker`, `model`. Words stay in JSONL; downstream
filters on `qa == []` via a join back to `videos.jsonl` on `video_id`.

### QA flags (`src/qa.py`)

`empty_transcript`, `no_segments`, `no_words`, `align_segment_only`,
`align_skipped`, `diarize_failed`, `lid_failed`, `lid_mismatch` (detected
language ≠ requested), `duration_mismatch` (>10% vs metadata),
`bad_timestamps`, `short_audio` (<5s).

### QA scores (`src/qa.py`, numeric, added per record)

Flags catch hard defects; scores grade soft quality for corpus filtering
and A-B engine comparisons. `mean_word_score` (wav2vec2 alignment
confidence in [0,1], `null` when no words), `speech_ratio` (segment-covered
seconds / duration), `empty_ratio` (blank-text segment fraction),
`repeat_max` (max repetition count of any 8-word phrase; the corpus shows
31x as lazy series intros, not model collapse), `arabic_ratio` (fraction
of letters in Arabic script — LID canary; the corpus is 1.000 across all
41 records).

### Text policy

Keep `transcript_raw` verbatim (ASR training) and `transcript_norm`
folded (alef/hamza → ا, tatweel stripped, diacritics stripped, ٠-٩→0-9)
for retrieval. The fold is stamped `norm_version` (`v1`) so future fold
changes stay identifiable. Audio is ephemeral by default: transcript +
metadata only (YouTube ToS / copyright).

## GPU & VRAM (RTX 5000 16GB, sm_75)

- `float16`, not `bfloat16` — Turing has no bf16 tensor cores (coherex
  `default` resolves to bf16 on cuda).
- Single video: ASR (~4GB) loads, transcribes, is released; aligner
  (~2GB) loads after. Playlist session: both resident (~6GB, needs ~7GB
  free — close Ollama/desktop GPU apps if OOM).
- Learned the hard way: `nvidia-smi` on Windows showed ~8GB already used
  by desktop processes; the pipeline still fit.

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `FileNotFoundError: [WinError 2]` right after VAD starts | coherex shells out to `ffmpeg` and it isn't on PATH → the run auto-shims imageio-ffmpeg to `data/bin/ffmpeg.exe`; if it still fails, pass `--ffmpeg-location` |
| Whole playlist downloads for a `video` run / checkpoint id is `PL...` | Watch URL carried `&list=`/`&index=` → use a bare `watch?v=` URL (plus `noplaylist` guard as backstop) |
| `UnicodeEncodeError: 'charmap'` | Windows cp1252 console → set `PYTHONUTF8=1` |
| `attempt failed ... ERROR: [download] ... timed out` | YouTube throttling (Egypt links); retry resumes (audio reuse + checkpoint) — avoid hammering, keep 1–2s delays |
| CUDA OOM | Batch auto-drops 8→4; if still OOM, free GPU VRAM (`nvidia-smi`) or `--device cpu` for alignment-only debug |
| `align_status=segment_only` | Aligner download/model failed; run continues with segment timestamps — check the logged traceback |

## Testing

```bash
python -m pytest -q   # 97 tests, all offline (mocked network/GPU boundaries)
```

`tests/test_contract.py` covers the schema/normalizer/parquet contract;
`test_youtube/qa/pipeline/parquet_extra.py` cover id parsing, QA gates and
numeric scores, retry + idempotent upsert, resume-before-network, and
writer edge cases; `test_score_wer.py` the scorer math and slice windows;
`test_viewer.py` the viewer's pure helpers; `test_diarize.py` the pure
speaker-annotation layer.

## Dataset viewer

```bash
python -m streamlit run src/viewer.py   # then attach an mp3 in the sidebar
```

Per-video stats (qa flags, timings), full segment table with click-to-play
windows (`st.audio` `start_time`/`end_time`) — doubles as the correction
aid for the WER reference (`docs/experiments/wer-eval-protocol.md`).

## Docker (CUDA) & Colab

```bash
docker build -t transcribe-engine .
docker run --gpus all -v %cd%/data:/app/data transcribe-engine \
  video "https://www.youtube.com/watch?v=VIDEO_ID" --to-parquet data/output/segments.parquet
```

`Dockerfile` pins `nvidia/cuda:12.8.1-runtime-ubuntu24.04` + torch
cu128 + system ffmpeg; the image runs the same CLI as local (Turing+
GPUs via nvidia-container-toolkit; `HF_TOKEN` through env at run time).
Built and smoke-tested on this box (entrypoint `--help` verified).

Colab: `notebooks/transcribe-engine-colab.ipynb` — T4 is the same sm_75
as the RTX 5000, so the fp16 defaults transfer unchanged. Cells cover
GPU check → install/clone → HF token from Colab secrets → transcribe →
inspect → Drive persistence.

## Project layout

```text
src/
  cli.py              argparse: video / playlist, engine knobs
  pipeline.py         orchestration, checkpoint, retry, upsert, manifest, prefetch
  transcribe.py       TranscribeConfig + TranscribeSession + transcribe_ar
  youtube.py          metadata, 16kHz wav, playlist expansion, noplaylist guard
  schema.py           VideoRecord JSONL contract
  qa.py               QA gates (flags, never drops)
  normalize_ar.py     versioned Arabic fold
  jsonl_to_parquet.py JSONL → parquet/pandas/csv
  score_wer.py        WER/CER scorer vs hand reference (slice support)
  make_reference.py   segment-aligned reference template from auto-captions
  lid.py              audio language ID (mms-lid-1024, CC-BY-NC)
  dialect.py          written-dialect tag (MARBERTv2: MAGHREB|LEV|MSA|GLF|EGY)
  viewer.py           Streamlit dataset viewer + segment audio playback
  diarize.py          Nemotron-3 speaker diarization (ungated, sole backend)
docs/
  ARCHITECTURE.md  module map + VRAM budget
  PLAN_V1_V2.md    v1 scope + branch log + v2
  DECISIONS.md     why each call was made (ADR-style)
  CURRENT-STATE.md what works right now + proven numbers
  ROADMAP.md       what's next, in order
Dockerfile         CUDA 12.8 + torch cu128 container (same CLI)
notebooks/
  transcribe-engine-colab.ipynb  T4 Colab runbook (sm_75-compatible)
```

Branch strategy: `main` + `feature/*` per step, merge with `--no-ff`,
one commit per step. See `docs/PLAN_V1_V2.md`.
