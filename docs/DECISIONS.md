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
