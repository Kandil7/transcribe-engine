# S22 — Human corrections and training export

| | |
|---|---|
| Phase | 5 |
| Depends on | S14, S15, S21 |
| Branch | `feat/S22-corrections-training-export` |
| Design sections | نواتج النظام والـ RAG › التصحيح البشري وبيانات التدريب؛ التمثيل المرجعي (النسخ) |
| ADRs | — |

## Goal
People correct words and speakers through the API, each save becomes a new transcript version with a
diff, and consented high-quality segments export as a training manifest.

## Interfaces
```python
@dataclass(frozen=True)
class Edit:
    segment_id: str; word_index_from: int; word_index_to: int; new_text: str
class SaveCorrection:   # use case
    async def __call__(self, tenant_id: str, transcript_id: str, base_version: int,
                       edits: Sequence[Edit], speaker_renames: Mapping[str, str]) -> int: ...  # new version
def diff_versions(a: CanonicalTranscript, b: CanonicalTranscript) -> TranscriptDiff   # pure
def export_manifest(items: Iterable[Segment], *, min_conf: float) -> Iterator[ManifestLine]
```

## Files
- `src/transcribe_engine/domain/{corrections,diff}.py`
- `src/transcribe_engine/application/use_cases/{save_correction,export_training}.py`
- `src/transcribe_engine/presentation/api/routes_corrections.py` — `POST /v1/transcriptions/{id}/versions`

## Rules `[D: التصحيح البشري وبيانات التدريب]`
- Unchanged words keep their timings; new or changed words get times from re-aligning that segment only (S14).
- Each save → new version, `source="human"`, diff vs the ASR version stored; optimistic concurrency
  on `base_version` (409 on conflict).
- Diffs feed the evaluation set and the terms dictionary.
- Corrected and high-confidence segments export as JSONL: `audio`, `offset_ms`, `duration_ms`, `text`,
  `source`, `snr_db`, `lang` — only with consent (S21 flag).
- Speaker renames apply to the whole version.
- New version triggers re-index (S18) and its events (S20).

## Acceptance criteria
- **AC-1** — `test_save_correction.py::test_unchanged_words_keep_times` (unit).
- **AC-2** — `::test_changed_segment_realigned_only` (unit, fake aligner call log).
- **AC-3** — `::test_stale_base_version_conflict` (unit) → 409 in API test.
- **AC-4** — `test_diff.py::test_diff_known_cases` (unit).
- **AC-5** — `test_export_training.py::test_consent_required` (unit).
- **AC-6** — `test_export_training.py::test_manifest_fields` (unit).

## Commit plan
1. `docs(S22): add spec`
2. `test(S22): add correction and export tests (xfail)`
3. `feat(S22): add edit model and version diff`
4. `feat(S22): add SaveCorrection with segment re-alignment`
5. `feat(S22): add corrections endpoint`
6. `feat(S22): add consented training manifest export`

## Open questions
- [x] Q1 — (resolved by: autopilot, 2026-11-27, D-061) Editor UI is not in scope of the backend; which client builds it? Not decided here: the backend exposes save and diff only; the client is the owner's choice.
