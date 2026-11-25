# S16 — Evaluation harness, robustness matrix, CI gate

| | |
|---|---|
| Phase | 4 |
| Depends on | S00, S12 |
| Branch | `feat/S16-evaluation-harness` |
| Design sections | اختيار النماذج والتقييم › مجموعة التقييم، المقاييس، مصفوفة المتانة، التقييم المستمر |
| ADRs | — |

## Goal
A standalone harness that runs the real pipeline Ports on a labeled set, reports every design metric
per condition bucket, and blocks merges that raise CER.

## Interfaces
```python
@dataclass(frozen=True)
class EvalItem:
    item_id: str; audio: str; offset_ms: int; duration_ms: int; text: str
    conditions: frozenset[str]; split: Literal["dev", "test"]
def cer(ref: str, hyp: str) -> float: ...   # after normalize()
def wer(ref: str, hyp: str) -> float: ...
def entity_error_rate(ref_entities: Sequence[Entity], hyp: str) -> float
def hallucination_rate(items: Sequence[ItemResult]) -> float
def word_timing_mae_ms(ref: Sequence[TimedWord], hyp: Sequence[TimedWord]) -> float
def der(ref: Sequence[SpeakerTurn], hyp: Sequence[SpeakerTurn]) -> float
```

## Files
- `evaluation/{metrics,dataset,run,report,augment}.py`, `evaluation/README.md`
- `evaluation/manifests/{dev,test}.jsonl` (paths only; audio outside git)
- `.github/workflows/nightly-eval.yml` (self-hosted GPU runner)
- `tests/unit/evaluation/test_metrics.py`

## Rules `[D: اختيار النماذج والتقييم]`
- 3–5 h varied audio; fixed dev/test split; tune only on dev.
- Written annotation guidelines (from S00) before any new reference.
- Same normalizer (`domain.text.normalize`) on reference and hypothesis.
- Metrics: WER/CER, Entity Error Rate, Hallucination Rate (text on silent refs or > 5 consecutive
  insertions), word timing MAE, DER, RTF p50/p95, peak VRAM, cost per audio hour.
- Robustness matrix: MUSAN noise and music at 20/10/5/0 dB, RIR reverb, Opus/AMR/MP3-32k codecs;
  each processing step (DeepFilterNet, Demucs) with and without; results per level.
- Real set bucketed by `AudioProfile` (clean/noise/music/telephony/reverb/overlap); report per bucket,
  never only an average.
- Report tagged with `pipeline_version`; changing the default engine needs a report.
- Regression gate: nightly 10-minute sample on GPU; CER increase > 0.5 points fails.
- The harness never writes to the eval data; the coding agent may run it, not edit references.

## Acceptance criteria
- **AC-1** — `test_metrics.py::test_cer_wer_known_values` (unit, textbook cases + Arabic cases).
- **AC-2** — `::test_normalizer_applied_both_sides` (unit): diacritics/hamza differences score 0.
- **AC-3** — `::test_hallucination_rate_definition` (unit).
- **AC-4** — `test_augment.py::test_snr_mix_exact` (unit): measured SNR of a mix within ±0.5 dB of target.
- **AC-5** — `evaluation/run.py --split dev` (eval) produces a report with every metric and bucket.
- **AC-6** — nightly workflow fails when CER rises > 0.5 vs the stored baseline (dry-run with a fake
  result file in `tests/unit/evaluation/test_gate.py`).

## Commit plan
1. `docs(S16): add spec`
2. `test(S16): add metric and gate tests (xfail)`
3. `feat(S16): add metrics (CER, WER, EER, hallucination, timing MAE, DER)`
4. `feat(S16): add dataset loader and runner over pipeline ports`
5. `feat(S16): add augmentation for robustness matrix`
6. `feat(S16): add per-bucket report`
7. `ci(S16): add nightly eval gate`

## Open questions
- [ ] Q1 — Word-timing MAE threshold for S14 AC-3. Proposed: set from the first run, then freeze.
