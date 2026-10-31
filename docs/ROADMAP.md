# Transcribe Engine — Roadmap

Ordered by payoff. v1 scope stays locked (transcript-only); v2 items are
unchanged from `PLAN_V1_V2.md` except where noted.

## Next (v1 hardening)

1. ~~GPU-soak a short playlist~~ **Done** (2026-09-07): 4/4 ok, session
   reuse, prefetch overlap, resume proven.
2. ~~Commit the tree~~ **Done**: landed via `feature/engine-fixes` merges;
   `main` clean at `1742e25`.
3. **Finish the playlist run** (paused mid-flight): 41 ok / 1 failed
   (retryable) / 15 unattempted; rerun the CLI command, then rebuild
   `segments.parquet` (`python -m src.jsonl_to_parquet data/output/
   videos.jsonl data/output/segments.parquet`).
4. **WER/CER spot-check**: infra ready (`src/score_wer.py` + 6 tests,
   audio + correctable draft on disk), protocol in
   `docs/experiments/wer-eval-protocol.md` — hand-correction by the user
   is the remaining step before the number exists.
5. **Add repo LICENSE** — user chose to defer; revisit before publishing.

## Then (v2, from the plan)

6. ~~Speaker diarization~~ **Done + GPU-verified**: `--diarize` with
   `nvidia/Nemotron-3-Diarization` default (ungated; beats pyannote on
   published DER). pyannote path optional behind `--diarize-model`
   (still needs its HF gate accepted).
7. ~~`vad_method=pyannote` option; vLLM backend~~ **Wired** (CLI
   `--vad-method` / `--backend vllm` pass-through to coherex). pyannote
   VAD needs `pyannote/segmentation-3.0` accepted (same click); vLLM
   needs `vllm` installed on the run box.
8. ~~Language auto-detect with explicit-`ar` default; dialect tag.~~
   **Done**: explicit `--language` pass-through; audio LID (`--lid`,
   `facebook/mms-lid-1024`, GPU-verified `ara` @ 0.998); written-dialect
   tag (`--dialect`, MARBERTv2 — **all 41 transcripts tagged `EGY`**,
   confidence mean 0.979). coherex refuses `language=None`, so ASR-side
   auto-detect stays out by design; the external LID covers detection.
9. Per-video QA scores: **metric layer done** (`qa_scores` —
   `mean_word_score`, `speech_ratio`, `empty_ratio`, `repeat_max`,
   backfilled on all 41 records); LID confidence and the 1–2h
   hand-transcribed eval set remain. Repeats across sibling lessons are
   genuine (see `experiments/repeat-artifact-resolution.md`); corpus
   overlap stats now exist too (`experiments/series-overlap.md`) —
   use them when building any train/eval split.
10. ~~Streamlit viewer; CUDA Dockerfile; Colab notebook~~ **Done**:
    `src/viewer.py`, `Dockerfile` + `.dockerignore`,
    `notebooks/transcribe-engine-colab.ipynb`.

## Deliberately out of scope

- Re-upload detection beyond duration checks; hard QA drops (use `qa`
  filters); multi-GPU (single RTX 5000 is the target box).
- Phrase-loop suppression heuristics — the repeat artifact was
  investigated and closed as genuine speech; suppression would damage
  legitimate repeated religious formulae.
