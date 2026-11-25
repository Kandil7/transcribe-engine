# S14 — Forced alignment

| | |
|---|---|
| Phase | 4 |
| Depends on | S12 |
| Branch | `feat/S14-forced-alignment` |
| Design sections | خط الأنابيب › 5. Forced Alignment؛ الـ Ports (Aligner) |
| ADRs | 0007 (is alignment mandatory) |

## Goal
Word-level timestamps for every engine, with a score per word and a segment-level fallback, correct
around digits and English words in Egyptian speech.

## Interfaces
```python
class Aligner(Protocol):
    name: str; revision: str
    async def align(self, audio: AudioRef, segments: Sequence[RawSegment], lang: str) -> Sequence[AlignedSegment]: ...
@dataclass(frozen=True)
class AlignedWord:
    text: str; start_ms: int; end_ms: int; align_score: float | None; lang: str; fallback: bool
def verbalize_for_alignment(text: str) -> tuple[str, Sequence[TokenMap]]   # digits → words, map back
```

## Files
- `src/transcribe_engine/domain/alignment_text.py` (verbalize + map back, pure)
- `src/transcribe_engine/infrastructure/ml/wav2vec2_aligner.py`
- `tests/unit/domain/test_alignment_text.py`, `tests/contracts/test_aligner_contract.py` (gpu)

## Rules `[D: 5. Forced Alignment]`
- Mandatory when `capabilities.native_word_timestamps` is false; optional otherwise.
- Arabic wav2vec2 model initially; compare CTC alternatives (e.g. NeMo Conformer CTC) in S16.
- Before alignment only: digits → words; the stored word keeps its original form.
- English words: English aligner or interpolated time from neighbors; `lang="en"` on the word.
- `align_score` per word; segment timing fallback when alignment fails (`fallback=true`).
- Alignment runs per chunk before merge (S10 midpoint rule needs word times).

## Acceptance criteria
- **AC-1** — `test_alignment_text.py::test_digits_verbalized_and_mapped_back` (unit): "50 جنيه" aligns as
  "خمسين جنيه", stored as "50".
- **AC-2** — `::test_english_tokens_marked` (unit).
- **AC-3** — `test_aligner_contract.py::test_word_boundaries_mae` (gpu): ≤ the S16 timing threshold on
  the hand-labeled sample.
- **AC-4** — `::test_failure_falls_back_to_segment_times` (contract, fake raising).
- **AC-5** — `test_process_job.py::test_alignment_mandatory_without_native_timestamps` (unit).

## Commit plan
1. `docs(S14): add spec`
2. `test(S14): add alignment tests (xfail)`
3. `feat(S14): add verbalize_for_alignment with token map`
4. `feat(S14): add aligner port, fake and wav2vec2 adapter`
5. `feat(S14): add fallback and code-switch handling`
6. `feat(S14): wire alignment into ProcessJob before merge`

## Open questions
- [ ] Q1 — Verbalize digits in MSA or Egyptian forms (خمسين / خمسون)? The audio is Egyptian.
  Proposed: Egyptian spoken forms; measure both in S16.
