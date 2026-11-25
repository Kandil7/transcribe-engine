# S17 — Speaker diarization

| | |
|---|---|
| Phase | 5 |
| Depends on | S14 |
| Branch | `feat/S17-diarization` |
| Design sections | خط الأنابيب › 6. Speaker Diarization (اختياري)؛ آلة الحالات › الإنجاز الجزئي |
| ADRs | — |

## Goal
Optional "who spoke when" on the whole file, with stable speaker ids, honest limits, and failures
that degrade to a warning instead of failing the job.

## Interfaces
```python
@dataclass(frozen=True)
class SpeakerTurn:
    speaker: str; start_ms: int; end_ms: int
class Diarizer(Protocol):
    name: str; revision: str; max_speakers: int | None
    async def diarize(self, audio: AudioRef, num_speakers: int | None) -> Sequence[SpeakerTurn]: ...
def assign_speakers(words: Sequence[Word], turns: Sequence[SpeakerTurn]) -> Sequence[Word]  # pure
```

## Files
- `src/transcribe_engine/domain/speakers.py`
- `src/transcribe_engine/infrastructure/ml/{pyannote_diarizer,sortformer_diarizer}.py`
- `tests/unit/domain/test_speakers.py`, `tests/contracts/test_diarizer_contract.py` (gpu)

## Rules `[D: 6. Speaker Diarization]`
- Runs on the full file, not per chunk, so `SPEAKER_00` is stable.
- Port declares `max_speakers`; Sortformer published model: 4. Requests above the limit use pyannote
  or return a warning.
- Words get the speaker with the largest time overlap; overlapping speech → `overlap=true`.
- Stereo files split by channel (S13) skip diarization: channel = speaker.
- Failure → `COMPLETED` with `warnings=["diarization_failed"]` `[D: الإنجاز الجزئي]`.
- Check model licenses before commercial use (pyannote models require accepting terms).

## Acceptance criteria
- **AC-1** — `test_speakers.py::test_max_overlap_assignment` (unit).
- **AC-2** — `::test_overlap_flag` (unit).
- **AC-3** — `test_process_job.py::test_diarization_failure_is_warning` (unit, fake raising).
- **AC-4** — `test_process_job.py::test_speakers_above_limit_uses_fallback_or_warns` (unit).
- **AC-5** — `test_diarizer_contract.py::test_two_speaker_fixture` (gpu): DER ≤ S16 baseline + margin.
- **AC-6** — `test_process_job.py::test_split_channels_skip_diarization` (unit).

## Commit plan
1. `docs(S17): add spec`
2. `test(S17): add diarization tests (xfail)`
3. `feat(S17): add speaker assignment`
4. `feat(S17): add diarizer port, fake and pyannote adapter`
5. `feat(S17): add Sortformer adapter with speaker limit`
6. `feat(S17): wire optional diarization with warning on failure`

## Open questions
- [ ] Q1 — Default engine: pyannote or Sortformer? Decide by DER in S16 on our audio.
