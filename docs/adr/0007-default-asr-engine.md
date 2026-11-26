# 0007. Default ASR engine
Status: Provisional
Date: 2026-11-26   Slice: S00 (partial)

## Context
The production default ASR engine must be chosen on our own Egyptian audio, before the infrastructure is
built, because it fixes the runtime, the VRAM and whether forced alignment is mandatory (design §اختيار
النماذج والتقييم). The S00 spike has no reference transcription yet (R-001), so no CER, WER, RTF or VRAM
number exists for any candidate on this machine. Only published figures are available, and those are
context, not evidence.

## Decision (provisional)
- **Local default on the bootstrap machine:** faster-whisper (CTranslate2), FP16 on the Quadro RTX 5000,
  profile `local-gpu` (D-001). It is chosen so the pipeline and the local demo can run. It is not a
  quality claim.
- **Production default:** not chosen yet. Candidates: Audar-ASR-V1-Turbo (served on vLLM, Qwen3-ASR format,
  not verified) and Cohere Transcribe Arabic 07-2026 (runtime not verified). Whisper large-v3 is the
  baseline. Falcon-ASR is excluded until its weights and a commercial license are published.
- **Forced alignment mandatory:** undecided. It is decided in S14 from the word-timing error measured on
  the dev set.
- **Runtime, VRAM and RTF:** not measured yet. Target GPU is the L4 (design default, spec Q2). This
  machine has a Quadro RTX 5000 (16 GB, Turing, no BF16), so the local numbers are not the production
  numbers.

## Consequences
- S12 may build the local faster-whisper adapter now. The vLLM adapter stays the production target
  (ADR-0005).
- Changing the production default requires an evaluation report, not a configuration change (design,
  "تغيير المحرك الافتراضي").

## Revisit when
- The dev hour is transcribed (R-001) and the S00 runs produce CER, WER, RTF and VRAM. Then this ADR
  becomes Accepted with those numbers.
- Falcon-ASR weights and a commercial license are published.
- Audar does not run on vLLM (AC-4). The fallback runtime is recorded here at that point.
