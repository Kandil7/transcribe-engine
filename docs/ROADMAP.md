# Transcribe Engine — Roadmap

Ordered by payoff. v1 scope stays locked (transcript-only); v2 items are
unchanged from `PLAN_V1_V2.md` except where noted.

## Next (v1 hardening)

1. **GPU-soak a short playlist** (3–5 videos): exercises session reuse,
   prefetch overlap, manifest, and resume after kill. Measures real
   videos/hour for capacity planning.
2. **Commit the tree**: `feature/gpu-run-fixes` + `feature/full-fixes` →
   `main` with `--no-ff`, one commit per step, then `git status` clean.
3. **Housekeeping**: resolve `videos.json`, add repo `LICENSE`, drop or
   adopt `pydantic` in `engine` extras.
4. **WER/CER spot-check**: hand-transcribe ~10 min, score the pipeline,
   record in a new `docs/experiments/` note. Gates v1 "done".

## Then (v2, from the plan)

5. Speaker diarization (`pyannote/speaker-diarization-community-1`),
   `speaker` column in parquet.
6. `vad_method=pyannote` option; vLLM backend for throughput.
7. Language auto-detect with explicit-`ar` default; dialect tag.
8. Per-video QA scores (empty-ratio, LID confidence, mean word score);
   1–2h hand-transcribed eval set.
9. Streamlit viewer; CUDA Dockerfile; Colab notebook.

## Deliberately out of scope

- Re-upload detection beyond duration checks; hard QA drops (use `qa`
  filters); multi-GPU (single RTX 5000 is the target box).
