# WER evaluation protocol (v1 gate)

Goal: one honest WER/CER number for the pipeline (Cohere-AR ASR + Silero
VAD + wav2vec2 align) against a hand-corrected reference. Chosen video:
`AeVhRpg0OuY` (650s, Egyptian-dialect religious lecture, full pipeline
output exists: 55 segments, 1,647 words, `qa=clean`).

## Why this video / why auto-captions can't be the reference

All four soak videos have NO manual captions, only machine auto-captions.
Auto-caption VTTs are rolling-window: raw text is ~3x inflated (4,832
"words" vs ~1,647 of real speech) — see `wer-spotcheck-01.md`. The correct
single-pass stream is recoverable from the inline `<00:..><c> word</c>`
tags, which carry each word exactly once: that yields a 1,426-word draft
(**76% distinct-token overlap** with the pipeline output) — usable as a
*correction base*, not as ground truth.

## Files already on disk

| Path | What |
|---|---|
| `data/raw_audio/eval/AeVhRpg0OuY_full.mp3` | the full audio, 5MB mono, listen offline |
| `data/raw_audio/eval/AeVhRpg0OuY_source.m4a` | raw downloaded source (~4MB) |
| `data/eval/AeVhRpg0OuY_autocaptions_draft.txt` | 1,426-word single-pass auto-caption stream (correction base) |
| `src/score_wer.py` | the scorer (30-test suite includes its 6 tests) |

## Steps to produce the number

1. Generate a segment-aligned correction template (auto-captions carry
   per-word timestamps; each of the 55 segments gets one `[start-end]`
   line prefilled with the draft text):
   ```
   python -m src.make_reference AeVhRpg0OuY
   ```
2. Play `data/raw_audio/eval/AeVhRpg0OuY_full.mp3` — the Streamlit
   viewer's `st.audio` plays exactly a selected segment's window — and
   correct `data/eval/AeVhRpg0OuY_reference_template.txt` line by line
   against the audio. Save as
   `data/eval/AeVhRpg0OuY_reference.txt` (keep UTF-8).
3. Score (understands the `[start-end]` line format and reports
   per-segment WER with the worst 5 lines):
   ```
   python -m src.score_wer AeVhRpg0OuY data/eval/AeVhRpg0OuY_reference.txt
   ```
   Optional window scoring of a part: `--slice 2:00-6:00`.
4. Paste the output into the results table below.

## Scoring semantics

- Both sides pass `normalize_ar` (NORM_VERSION fold) first, so diacritics,
  hamza/alef variants, tatweel and Arabic numeral spellings are not errors.
- WER = (subs+del+ins)/ref_words via word-DP; CER = char edit distance /
  ref chars (spaces removed).
- Faithful segments only: compare `transcript_raw`, not `transcript_norm`.

## Results

_(pending — fill in after step 3)_

| run | slice | WER | CER | ref words | hyp words | notes |
|---|---|---|---|---|---|---|
| | full video | | | | | |
