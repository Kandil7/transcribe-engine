# Transcribe Engine — Current State

Updated: 2026-09-07. `main` is green plus unmerged work in the tree
(see `git status`; intended for `feature/full-fixes` → `main`, `--no-ff`).

## What works right now

- End-to-end GPU run on RTX 5000 (torch 2.11.0+cu128, `float16`):
  17.4-min Arabic video → **112 segments, 2,622 word timestamps,
  `align=ok`**, VAD+ASR in ~44s.
- `videos.jsonl` (upserted), `segments.parquet` (112×13, 0 nulls),
  `checkpoint.db`, `playlist_summary.json`, `manifest.json`.
- Old JSONL lines (pre-`qa`/`license`/`timings` schema) still parse —
  new fields backfill defaults.
- 24/24 tests pass, all offline (mocked network/GPU).

## Numbers to beat

| Metric | Value |
|---|---|
| VAD+ASR, 1041s audio, batch 8, fp16 | ~44s wall |
| Aligner download (one-time, ~1.2GB, throttled link) | ~15 min |
| Model load from HF cache (4.1GB) | ~2s |
| ASR resident | ~4GB VRAM; +aligner ~6GB in playlist sessions |

## Playlist soak (2026-09-07, `--max-videos 4`, 57-video playlist)

- **4/4 ok, 0 failed, 627.7s total.** Session loaded once; aligner loaded
  once and reused; prefetch overlapped downloads with GPU work.
- `j7c3F6D_R1U`: 598 segs (5616s audio); `ZXWzWWXzPmU`: skipped, zero
  network (resume proven); `AeVhRpg0OuY`: 55 segs in ~41s;
  `gBZl6PiEZi0`: 113 segs in ~102s. All `align=ok`, all `qa=clean`.
- `segments.parquet` now 878 rows (112+598+55+113). 6GB resident held,
  no OOM with ~8GB free.
- Spot-check: `docs/experiments/wer-spotcheck-01.md` (no numeric WER —
  no manual subs exist; possible phrase-loop artifact logged).

## Known limitations

- Full 57-video playlist not yet run (soak covered the session/prefetch/
  resume path; remaining risk is only YouTube throttling over hours).
- YouTube throttling on this link (~0.3–1 MB/s): audio re-downloads and
  model fetches are slow but resumable.
- `videos.json` (untracked, repo root) is not ours — left alone; delete or
  move to `data/` if junk.
- No license file for this repo yet — add one before publishing.
- `pydantic` is listed in `engine` extras but unused (dataclasses carry
  the contract); either use it or drop it.
