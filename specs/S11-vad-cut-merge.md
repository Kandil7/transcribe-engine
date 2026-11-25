# S11 — VAD with cut and merge

| | |
|---|---|
| Phase | 3 |
| Depends on | S10, S00 |
| Branch | `feat/S11-vad-cut-merge` |
| Design sections | خط الأنابيب › 2. VAD مع Cut & Merge؛ التقسيم (قواعد التقسيم) |
| ADRs | 0007 (engine → `max_chunk_seconds`) |

## Goal
Real speech regions from Silero VAD, merged into chunks close to the engine's maximum length, cut
at the longest internal silence, so the ASR never sees mid-word cuts or tiny context-less chunks.

## Interfaces
```python
@dataclass(frozen=True)
class SpeechRegion:
    start_sample: int; end_sample: int; prob: float
class VoiceActivityDetector(Protocol):
    name: str; revision: str
    async def detect(self, audio: AudioRef, params: VadParams) -> Sequence[SpeechRegion]: ...
@dataclass(frozen=True)
class VadParams:
    threshold: float; min_silence_ms: int; min_speech_ms: int
def cut_and_merge(regions: Sequence[SpeechRegion], *, target_ms: int, max_ms: int, pad_ms: int,
                  overlap_ms: int, silences: Sequence[SampleSpan]) -> Sequence[SampleSpan]
```

## Files
- `src/transcribe_engine/domain/vad.py` (cut_and_merge, pure)
- `src/transcribe_engine/infrastructure/ml/silero_vad.py` (extra `ml`)
- `tests/unit/domain/test_vad_cut_merge*.py`, `tests/contracts/test_vad_contract.py` (gpu or cpu-ml)

## Rules `[D: 2. VAD مع Cut & Merge]`
- Merge adjacent regions up to the engine's `max_chunk_seconds` (usually 20–30 s).
- Padding ~200 ms each side.
- A region longer than max is cut at its longest internal silence; only without any silence use a
  fixed window with 1–2 s overlap (recorded as `overlap_with_prev`).
- Region offsets map to original-file samples; tested with property tests.
- VAD runs in the CPU stage (`PrepareChunks`, S10) `[D: تشغيل الـ GPU Worker]`.
- VAD params come from `PipelineConfig.vad_params` (part of the result key, S03).

## Acceptance criteria
- **AC-1** — `test_vad_cut_merge_properties.py::test_every_speech_sample_covered` (Hypothesis).
- **AC-2** — `::test_no_chunk_exceeds_max_plus_pad` (Hypothesis).
- **AC-3** — `test_vad_cut_merge.py::test_cut_at_longest_silence` (unit).
- **AC-4** — `test_vad_cut_merge.py::test_fixed_window_only_without_silence` (unit): overlap set.
- **AC-5** — `test_vad_contract.py::test_silence_file_no_regions`, `::test_tone_bursts_found` (contract, ml).
- **AC-6** — `test_prepare_chunks.py::test_uses_engine_max_chunk_seconds` (unit, fakes): VAD runs in
  the CPU stage and the plan respects the configured engine's `max_chunk_seconds`.

## Commit plan
1. `docs(S11): add spec`
2. `test(S11): add cut-and-merge and VAD contract tests (xfail)`
3. `feat(S11): add cut_and_merge`
4. `feat(S11): add Silero VAD adapter`
5. `feat(S11): wire Silero VAD into PrepareChunks`

## Open questions
- [ ] Q1 — Minimum chunk length (very short isolated words). Proposed: merge into neighbor if gap
  < 1 s, else keep; measured in S16.
