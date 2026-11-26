# S00 report — model selection spike (partial)

Status: **partial** (2026-11-26). The engine decision is **provisional** (ADR-0007). No model has been
measured on reference data, so no accuracy or throughput numbers are reported here.

## What exists
| Item | State | Where |
|---|---|---|
| Annotation guidelines (AC-1) | done; covered by a test | `evaluation/guidelines.ar.md`, `tests/unit/evaluation/test_guidelines.py` |
| Manifest format, validator, coverage gate (AC-2 tooling) | done; unit-tested | `evaluation/spike/manifest.py`, `evaluation/spike/validate_manifest.py` |
| Dev manifest with ≥ 60 min of transcribed audio (AC-2 data) | **missing** | needs a human transcriber, see R-001 |
| Candidate runner and notebook (`run.ipynb`) | not written | nothing to run against yet |
| CER, WER, hallucination, RTF, VRAM per model (AC-3) | **not measured** | needs R-001 for CER/WER; RTF/VRAM needs audio |
| Audar-ASR-V1-Turbo on vLLM (AC-4) | **not tested** | no command or version recorded |
| ADR-0007 (AC-5) | written as **Provisional** | `docs/adr/0007-default-asr-engine.md` |

## Why the spike is partial
- **No reference transcription.** An agent cannot be its own ground truth (prompt §5). The dev hour
  must be transcribed by a person under `evaluation/guidelines.ar.md`, from in-house recordings kept
  in `data/` outside git (spec Q1). This is R-001 in `docs/REVIEW_QUEUE.md`.
- **No local audio in the repository.** Without audio, RTF and VRAM cannot be measured.
- **Model weights were not downloaded.** Audar, Cohere and Whisper large-v3 were not fetched, so
  no runtime was tested.

## Results table
Not produced. Published leaderboard numbers are context only, never the decision basis (spec rule).

| Model | CER | WER | Hallucination | RTF p50 / p95 | Peak VRAM | Runtime |
|---|---|---|---|---|---|---|
| faster-whisper, large-v3 class (local profile, D-001) | not measured | not measured | not measured | not measured | not measured | faster-whisper, FP16, Quadro RTX 5000 |
| Audar-ASR-V1-Turbo | not measured | not measured | not measured | not measured | not measured | vLLM, not tested |
| Cohere Transcribe Arabic (07-2026) | not measured | not measured | not measured | not measured | not measured | not tested |

## Next steps
1. A person transcribes ≥ 60 min of dev audio per the guidelines (R-001). Then
   `uv run python -m evaluation.spike.validate_manifest evaluation/spike/manifest.jsonl --require-coverage`.
2. Write the runner and `run.ipynb`; measure RTF, peak VRAM and CER/WER on the dev set.
3. Test the Audar-on-vLLM command and record the version (AC-4), or the fallback runtime.
4. Replace the provisional part of ADR-0007 with measured numbers; mark S00 `done`.
