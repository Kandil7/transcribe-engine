# S10 — Chunk plan, fan-out, merge (Fake ASR, end-to-end)

| | |
|---|---|
| Phase | 2 |
| Depends on | S09 |
| Branch | `feat/S10-chunking-fanout-merge` |
| Design sections | خط الأنابيب › التقسيم والمعالجة المتوازية والتجميع؛ آلة الحالات (المراحل، الإنجاز الجزئي) |
| ADRs | 0003 |

## Goal
End to end with fakes: upload → ingest → chunk plan → concurrent fake ASR per chunk → ordered merge
→ persisted transcript → `COMPLETED`. Proves ordering, idempotent resume, and partial-failure policy
before any real model exists.

## Interfaces
```python
@dataclass(frozen=True)
class Chunk:
    chunk_id: str; job_id: str; idx: int; total: int
    start_sample: int; end_sample: int; pad_before: int; pad_after: int
    sample_rate: int; media_sha256: str; config_hash: str; overlap_with_prev: int = 0

def plan_chunks(regions: Sequence[SpeechRegion], *, max_samples: int, pad: int, total_samples: int,
                media_sha256: str, config_hash: str, job_id: str) -> tuple[Chunk, ...]
def merge(chunks: Sequence[Chunk], results: Sequence[ChunkResult]) -> MergedWords
def validate_merge(words: MergedWords, duration_samples: int) -> list[str]   # warnings

@dataclass(frozen=True)
class Word:
    text: str; start_ms: int; end_ms: int; conf: float | None; chunk_idx: int
class PrepareChunks:  # use case, CPU stage after normalization, before hand-off
    async def __call__(self, job: Job, lease: Lease) -> None: ...
class ProcessJob:   # use case, handler for queue "gpu"
    async def __call__(self, job: Job, lease: Lease) -> None: ...
```

## Files
- `src/transcribe_engine/domain/{chunks,merge,transcript}.py`
- `src/transcribe_engine/application/use_cases/{prepare_chunks,process_job}.py`
- `src/transcribe_engine/application/ports/{asr,vad}.py` (minimal, extended in S11/S12)
- `tests/fakes/{asr,vad}.py`; `tests/unit/domain/test_chunks*.py`, `test_merge*.py`;
  `tests/integration/test_end_to_end_fake.py`

## Rules `[D: التقسيم والمعالجة المتوازية والتجميع]`
- The plan is built on the CPU side after normalization (VAD runs on CPU `[D: تشغيل الـ GPU Worker]`),
  persisted, and only then handed off to the GPU queue; `ProcessJob` reads the stored plan.
- Split on speech regions; padding recorded separately from core bounds; integer samples only.
- Plan persisted in `chunks` before processing; resume skips chunks whose result exists (chunk_id).
- Audio read by S3 Range GET on the normalized WAV; no per-chunk files.
- Concurrency bounded by a semaphore (config, initial 32); each chunk result saved immediately.
- Merge: all `idx` 0..total−1 present once; order by `idx`; `global = start_sample − pad_before + local`;
  keep a word only if its midpoint is inside its chunk's core bounds.
- Validation: monotonic times, no word beyond duration, speech-coverage ratio vs VAD.
- Permanent chunk failure: job `COMPLETED` with `warnings=["chunk_failed:<idx>"]` and a timed gap
  marker, or `FAILED` when the tenant requires complete text (tenant flag) `[D: الإنجاز الجزئي]`.
- Progress = `chunks_done / chunks_total` `[D: التقسيم]`.

## Acceptance criteria
- **AC-1** — `test_merge_properties.py::test_completion_order_irrelevant` (Hypothesis, 100 shuffles):
  byte-identical merged output.
- **AC-2** — `test_merge_properties.py::test_split_merge_preserves_times` (Hypothesis): zero-sample tolerance.
- **AC-3** — `test_merge.py::test_midpoint_rule_dedupes_padding` (unit): word in overlap appears once.
- **AC-4** — `test_merge.py::test_missing_idx_raises` (unit).
- **AC-5** — `test_chunks.py::test_edge_cases` (unit): silent file, single chunk, region longer than max.
- **AC-6** — `test_end_to_end_fake.py::test_upload_to_completed` (integration).
- **AC-7** — `test_end_to_end_fake.py::test_kill_mid_job_resumes_without_reprocessing` (integration):
  fake ASR call count per chunk_id = 1 across the restart.
- **AC-8** `[D: الإنجاز الجزئي]` — `test_process_job.py::test_permanent_chunk_failure_policy` (unit, both tenant settings).

## Commit plan
1. `docs(S10): add spec`
2. `test(S10): add chunk, merge and end-to-end tests (xfail)`
3. `feat(S10): add Chunk and plan_chunks`
4. `feat(S10): add merge with midpoint rule and validation`
5. `feat(S10): add minimal ASR and VAD ports with fakes`
6. `feat(S10): add PrepareChunks on the CPU path before hand-off`
7. `feat(S10): add ProcessJob with bounded concurrency and resume`
8. `feat(S10): persist transcript and complete job`

## Open questions
- [ ] Q1 — Work units of 10–20 min across GPUs: proposed out of scope until one file exceeds a single
  GPU's timeout budget (design: "للملفات الطويلة جدًا فقط").
