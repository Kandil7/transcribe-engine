# Experiment 01 — Spot-check vs reference captions (AeVhRpg0OuY)

Date: 2026-09-07. Video: `AeVhRpg0OuY` (650s, Egyptian-dialect religious
lecture). Pipeline output: 55 segments, 1,647 words, `align=ok`, `qa=clean`.

## Method

1. Looked for manual (`subtitles`) Arabic captions on all 4 soak videos —
   none exist, only `automatic_captions`.
2. Tried scoring against YouTube auto captions as a weak reference
   (both sides folded with `normalize_ar`, stdlib edit distance).

## Result: reference rejected, no numeric WER claimed

The auto-caption VTT holds ~4,836 words vs our 1,647 for the same 650s
(~3:1) — rolling-window duplication in the auto track, not real content.
Raw agreement numbers were WER=0.72 / CER=0.67, which measure the
reference's noise, not our quality. **Do not quote these as quality.**

## Qualitative read (6 sampled segments: head/middle/tail)

- Fluent, coherent Egyptian Arabic; religious formulae correct
  (صلى الله عليه وسلم, عز وجل); dialect words plausible.
- Hadith wording close to canonical
  ("العلم بالتحلم، الحلم بالتحلم" vs إنما العلم بالتعلم...).
- **Artifact hypothesis**: long repeated phrases recur near-verbatim
  ~600s apart ("عمر بن الخطاب ست سنين قتل..." in seg 1 and seg 5) plus
  local stutters (لما لما, لسان لسان). Possibly genuine speaker
  repetition, but identical multi-second passages smell like
  VAD-chunk/decoder loops.

## Conclusion

- Verdict: plausible, dialect-correct, needs a real number.
- Next: hand-transcribe ~10 min (or find a video with manual subs),
  compute true WER/CER, and test whether adjacent-duplicate-phrase
  suppression or VAD-merge tuning removes the loop artifact.
- Reusable harness (not committed, lives in the opencode temp dir):
  fetch `ar` auto-subs → VTT dedupe → normalize → edit distance.
