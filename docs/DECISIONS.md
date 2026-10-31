# Transcribe Engine — Decisions (ADR-style)

Short log of *why* each non-obvious call was made. Newest last. Revisit a
decision when its "revisit if" condition fires.

## 1. `float16`, not `bfloat16`, on the RTX 5000

- Context: coherex `compute_type="default"` resolves to bf16 on cuda.
- Decision: default to `float16` (`src/transcribe.py:TranscribeConfig`).
- Why: Turing sm_75 has no bf16 tensor cores; bf16 buys nothing and risks
  slow/unsupported paths.
- Revisit if: Ampere+ GPU (bf16 becomes the right default).

## 2. `noplaylist=True` + bare watch URLs

- Context: a `video` run with `&list=`/`&index=` params made yt-dlp
  download the whole playlist and record the playlist id as `video_id`.
- Decision: `noplaylist=True` in every single-video yt-dlp call, a
  playlist-container guard in `extract_metadata`, URL-first video ids,
  and docs mandating bare `watch?v=` URLs.
- Revisit if: yt-dlp changes watch+list semantics (guard logs will show it).

## 3. ffmpeg shim instead of system requirement

- Context: coherex hard-codes `ffmpeg` on PATH (`coherex/audio.py`);
  Windows hosts often have only imageio-ffmpeg's versioned binary.
- Decision: `ensure_ffmpeg_on_path` copies it to `data/bin/ffmpeg.exe`
  (gitignored) and prepends PATH, instead of editing site-packages or
  vendoring ffmpeg.
- Revisit if: coherex makes the ffmpeg path configurable upstream.

## 4. Audio reuse validated by duration + delete-only-owned

- Context: retries re-downloaded 86MB per attempt (Egypt bandwidth), and a
  `finally` block once deleted a good cached wav.
- Decision: reuse a wav only if >1MB *and* its duration matches metadata
  (±5%/10s); `finally` deletes only attempt-owned files.
- Revisit if: videos get re-uploaded under the same id with new audio
  (duration check mostly covers this).

## 5. `TranscribeSession` over per-video loads

- Context: playlists paid the ~4GB weight load + HF metadata roundtrips
  per video.
- Decision: one resident ASR + aligner for the whole playlist
  (~6GB resident, ~7GB free needed); `transcribe_ar` stays as the
  single-shot wrapper. Plus 1-thread audio prefetch overlapping GPU work.
- Revisit if: VRAM < 7GB free (fall back to per-video sessions).

## 6. QA flags, never QA drops

- Context: one bad video must not poison a playlist run, but silent bad
  rows poison datasets.
- Decision: `src/qa.py` flags records; everything is still written;
  downstream filters `qa == []`.
- Revisit if: a corpus needs hard gates (add `--strict-qa` then).

## 7. JSONL upsert on `video_id`

- Context: re-runs appended duplicate lines for the same video.
- Decision: rewrite-out-same-id on every write (files are small).
- Revisit if: JSONL grows past ~100k lines (switch to sqlite-backed store).

## 8. Versioned normalizer

- Context: `transcript_norm` folds are lossy (`ة→ه`, hamza stripped);
  future fold tweaks would silently mix corpora.
- Decision: `NORM_VERSION` stamped per record; raw stays verbatim.
- Revisit if: the fold changes (bump to `v2`, keep reader back-compat).

## 9. Diarization: annotate, never fail

- Context: v2 wants `speaker` per segment; pyannote models are gated and
  every failure mode (403, OOM, model change) must not kill a playlist.
- Decision: `--diarize` runs pyannote after alignment and annotates
  segments/words in place; failures log, set `diarize_status="failed"`
  and raise the `diarize_failed` QA flag instead of aborting.
- Revisit if: diarization becomes a hard requirement (then gate on it
  like alignment instead of flagging).

## 10. Engine knobs are pass-through, not wrappers

- Context: v2 listed "pyannote VAD option" and "vLLM backend" as features.
- Fact: coherex already implements both (`vad_method` ∈ silero|pyannote,
  `backend` ∈ local|vllm with managed server). Re-implementing would fork
  engine logic we don't own.
- Decision: `TranscribeConfig` + CLI pass the knobs through to
  `coherex.load_model` unchanged; the manifest records what ran.
- Revisit if: coherex drops/renames a parameter (our tests pin the
  config surface, GPU soak would catch the rest).

## 11. Corpus dedup is dataset-time, not pipeline-time

- Context: `i41KPdjG0O8` ↔ `R0tJASk3fLw` are a re-upload pair
  (8-gram Jaccard 0.92) and series lessons quote each other heavily.
- Decision: transcription stays faithful per video; dedup/leakage
  filtering happens at training-split build (see
  `experiments/series-overlap.md`).
- Revisit if: a downstream consumer asks for a deduped view (offer a
  dataset-build helper, don't change the pipeline).

## 12. Nemotron-3 as the default diarizer

- Context: pyannote models are gated (403 for this account); the user
  named `Nemotron-3-Diarization`.
- Fact: `nvidia/Nemotron-3-Diarization` is ungated (OpenMDW), 99.2M
  params, transformers-native since transformers 5.22, and beats the
  pyannote baseline on every published DER benchmark.
- Decision: default `--diarize-model` to Nemotron; keep the pyannote
  path selectable via the same flag. Decode audio via the ffmpeg CLI
  shim instead of `transformers.audio_utils.load_audio` (torchcodec
  needs shared-FFmpeg DLLs Windows doesn't ship here).
- Revisit if: transformers drops the architecture or a stronger open
  model lands.

## 13. Per-model HF cache-root resolution

- Context: this machine's HF caches are split across two roots (legacy
  `HF_HOME` layout vs `HF_HOME/hub`); after a huggingface_hub upgrade the
  hub resolved one root and tried to re-download 4.13GB of weights that
  existed in the other, failing on disk space for hours of retries.
- Decision: `resolve_cache_dir(model_id)` picks the root that actually
  holds the model by content size (stub dirs from failed downloads don't
  count); wired into every model load (ASR `download_root`, aligner
  `model_dir`, diarizer `cache_dir`).
- Revisit if: the caches get unified into one root (then the helper can
  be deleted).

## 14. Audio LID is transient and opt-in

- Context: roadmap wants LID confidence; `facebook/mms-lid-1024` is a
  1B-param CC-BY-NC model — too heavy to keep resident next to ASR, and
  the license restricts commercial use of the model itself (fine for
  this research corpus, flagged in the docs).
- Decision: `--lid` opt-in; the model loads, scores a 30s middle clip,
  and is dropped before the next video. Codes are MMS ISO 639-3; the QA
  `lid_mismatch` flag compares via a small 639-1→639-3 map. Detection
  lands on the record (`lid_lang`, `lid_confidence`), never gates.
- Revisit if: a permissive small LID model lands (then make it default)
  or if commercial deployment matters (drop MMS LID entirely).

## 15. Local-first model loading, process-isolated prefetch

- Context: every model load hit the HF API (revision/etag round-trips)
  and could silently re-download weights that existed in another cache
  root; sequential multi-GB loads in one process also exhaust Windows
  commit even when each model fits alone (freed pages return lazily).
- Decision: `load_local_first(loader)` attempts every load cache-only
  (`HF_HUB_OFFLINE=1`) and only goes online on a genuine cache miss;
  `cli prefetch` verifies every pipeline model in one subprocess each,
  so memory is reclaimed at process exit. Statuses report `local` vs
  `downloaded`.
- Revisit if: huggingface_hub grows a first-class offline-first mode
  (then the wrapper can shrink to it).

## 16. Written-dialect tag on MARBERTv2

- Context: the roadmap wants a dialect tag; audio dialect ID would need
  the deleted audio, but transcripts exist for every record.
- Fact: `IbrahimAmin/marbertv2-arabic-written-dialect-classifier` has
  named labels (`MAGHREB|LEV|MSA|GLF|EGY`) covering Egyptian; the more
  downloaded alternative ships anonymous `LABEL_0..17` (unusable without
  a mapping). Trained on written text — applied to transcripts, no audio.
- Decision: `--dialect` opt-in; classification averages softmax over
  spread text windows (start/middle/end, MARBERT caps at 512 tokens);
  results land on the record as metadata only (never QA-flags — a
  dialect is not a defect).
- Revisit if: a finer-grained Arabic dialect model (city/governorate
  level) lands with clean labels.

## 17. Long videos need memory headroom, not retries

- Context: 100+ minute videos (200MB+ wavs) failed all 3 retry attempts,
  degraded to `align=segment_only`, or hung a subprocess reader thread —
  all with `MemoryError`/`os error 1455` at coherex's whole-file audio
  load (~800MB transient: ffmpeg pipe buffer + int16 + float32 copies).
- Fact: the same videos completed clean with full alignment once commit
  headroom existed (Docker Desktop VM stopped, hung prior process
  killed, LM Studio closed). The retries were never the fix; headroom
  was.
- Decision: keep the never-fail degradation (QA flags, run continues)
  and treat commit headroom as an operational precondition for
  long-video batches — check free commit before big runs rather than
  trusting retries to recover.
- Revisit if: coherex streams audio instead of loading whole files
  (then the constraint disappears), or the pipeline chunks long audio
  before the engine.
