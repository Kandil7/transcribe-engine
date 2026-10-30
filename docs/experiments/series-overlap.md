# Experiment 03 — Corpus overlap & near-duplicate detection

Date: 2026-10-30. Scope: all 41 completed transcripts
(`transcript_raw`, normalized with `normalize_ar`, 8-word shingle Jaccard).

## Findings

- 46 of 820 pairs share any 8-gram; 12 share <1% Jaccard (cross-lesson
  shared hadith quotes — expected for a teacher's lecture series).
- **Near-duplicate re-upload candidate (Jaccard 0.920, 1,526 shared
  shingles): `i41KPdjG0O8` ↔ `R0tJASk3fLw`.** These two "videos" are the
  same lecture. Training on both double-counts ~1,600 segments.
- Heavy-sharing pairs 0.31–0.49 (`AeVhRpg0OuY`/`SEbxw18U_7c`,
  `LkNl6ULOUDs`/`fIHUry17r3o`, `tlNcdOGU7Es`/`SEbxw18U_7c`) are same-series
  lessons that recap prior material — legitimate for text, but their
  shared passages should be dropped when building an ASR training split
  to avoid train/test leakage.
- Max Jaccard otherwise: 0.492. No other re-upload candidates above the
  0.8 threshold.

## Recommendation

- Add a corpus-level dedup step before any training/eval split: keep one
  of `i41KPdjG0O8`/`R0tJASk3fLw`, and for series lessons drop passages
  shared with earlier episodes when the eval set draws from the same
  playlist. Do NOT do this inside the pipeline (transcription must stay
  faithful per video) — this belongs at dataset-build time.
- Metric script (stdlib + `normalize_ar`): shingle-set Jaccard per pair,
  threshold 0.8 for re-upload candidates, one-shot in the opencode temp
  dir; results here are the durable record.
