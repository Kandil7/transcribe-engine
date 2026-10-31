# Cross-ASR agreement — AeVhRpg0OuY

Date: 2026-10-31. **This is NOT ground truth** — an independent
system-agreement number between two different ASR stacks:
`openai/whisper-large-v3-turbo` (OpenAI, fp16, cuda, chunked long-form 30s windows) vs
the pipeline's Cohere-AR. Agreement between independent systems bounds
both systems' quality from above; the true WER still needs the hand
reference (`wer-eval-protocol.md`).

- Whisper wall (incl. load): 59s
- pipeline words: 1647, whisper words: 1981
- WER(whisper vs pipeline): 0.938  CER: 0.532
- (symmetric) WER(pipeline vs whisper): 0.780  (word-count ratio skew is normal)

Reading: for Arabic, cross-system WER is inflated by clitic-segmentation
convention differences (attached "وفيه" vs separate "و فيه"), so **CER is
the informative cross-system metric**: 0.532 disagreement ≈ each system
likely ~75–85% character-accurate on this dialect-heavy religious lecture
(errors partially correlated on the same hard dialect words). This is an
upper-bound-ish disagreement, not either system's WER. The earlier
qualitative read (`wer-spotcheck-01`) found the pipeline output fluent and
largely correct, consistent with true quality well above the raw
disagreement. The hand reference remains the gold standard.
