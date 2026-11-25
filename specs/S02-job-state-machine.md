# S02 — Job state machine

| | |
|---|---|
| Phase | 2 |
| Depends on | S01 |
| Branch | `feat/S02-job-state-machine` |
| Design sections | آلة الحالات والاعتمادية › الحالات، آليات الاعتمادية |
| ADRs | 0006 (stage hand-off between queues) |

## Goal
A pure domain model of job states, events and allowed transitions, with error codes, stages and
warnings, that every other slice uses. No I/O.

## Scope
- In: `JobState`, `JobEvent`, `JobStage`, `ErrorCode`, `Warning` codes, `transition()`, retry
  decision, backoff calculation, timeout formula.
- Out (→ S05): DB CHECK constraint. (→ S06): leases, heartbeats, reconciler, fencing.

## Interfaces
```python
class JobState(StrEnum):
    PENDING_VALIDATION = "PENDING_VALIDATION"; QUEUED = "QUEUED"; PROCESSING = "PROCESSING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"; COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELLED = "CANCELLED"
    @property
    def is_terminal(self) -> bool: ...

class JobStage(StrEnum):  # order matters
    VALIDATING, NORMALIZING, PROFILING, VAD, ASR, ALIGNING, DIARIZING, POSTPROCESSING, PERSISTING

class JobEvent(StrEnum):
    VALIDATED, CACHE_HIT, VALIDATION_FAILED, CLAIMED, STAGE_HANDOFF, SUCCEEDED,
    TRANSIENT_ERROR, PERMANENT_ERROR, LEASE_EXPIRED, RETRY_DUE, CANCEL_REQUESTED

class ErrorCode(StrEnum):
    INVALID_MEDIA, UNSUPPORTED_FORMAT, TOO_LONG, TOO_LARGE, UNSUPPORTED_LANGUAGE,
    ATTEMPTS_EXHAUSTED, POISON_JOB, TIMEOUT, INTERNAL

@dataclass(frozen=True)
class Transition:
    to: JobState
    error_code: ErrorCode | None = None

def transition(state: JobState, event: JobEvent, *, attempt_count: int, max_attempts: int) -> Transition:
    """Raises InvalidTransitionError for pairs not in the table."""

def backoff(attempt: int, *, base: timedelta, cap: timedelta, jitter: float) -> timedelta: ...
def processing_timeout(duration_ms: int, *, rtf_p95: float, factor: float = 3.0,
                       overhead: timedelta = timedelta(seconds=120)) -> timedelta: ...
```

## Files
- `src/transcribe_engine/domain/jobs.py`
- `tests/unit/domain/test_jobs.py`, `tests/unit/domain/test_jobs_properties.py`

## Rules (transition table)
| From | Event | To | Source |
|---|---|---|---|
| PENDING_VALIDATION | VALIDATED | QUEUED | `[D: الحالات]` |
| PENDING_VALIDATION | CACHE_HIT | COMPLETED | `[D: الحالات]` |
| PENDING_VALIDATION | VALIDATION_FAILED | FAILED (code from caller) | `[D: الحالات]` |
| QUEUED | CLAIMED | PROCESSING | `[D: الحالات]` |
| PROCESSING | SUCCEEDED | COMPLETED | `[D: الحالات]` |
| PROCESSING | STAGE_HANDOFF | QUEUED | `[ADR-0006]` |
| PROCESSING | TRANSIENT_ERROR, attempts < max | RETRY_SCHEDULED | `[D: آليات الاعتمادية]` |
| PROCESSING | TRANSIENT_ERROR, attempts ≥ max | FAILED(ATTEMPTS_EXHAUSTED) | `[D: آليات الاعتمادية]` |
| PROCESSING | PERMANENT_ERROR | FAILED | `[D: آليات الاعتمادية]` |
| PROCESSING | LEASE_EXPIRED, attempts < max | RETRY_SCHEDULED | `[D: آليات الاعتمادية]` |
| PROCESSING | LEASE_EXPIRED, attempts ≥ max | FAILED(POISON_JOB) | `[D: آليات الاعتمادية]` |
| RETRY_SCHEDULED | RETRY_DUE | QUEUED | `[D: الحالات]` |
| any non-terminal | CANCEL_REQUESTED | CANCELLED | `[D: الحالات]` |

- Terminal states accept no event `[D: الحالات]`; a new run is a new job.
- `attempt_count` is incremented at claim time, before any work `[D: آليات الاعتمادية]`.
- Backoff is exponential with jitter `[D: آليات الاعتمادية]`; base/cap/jitter are config (Q2).
- Timeout = `duration × RTF_p95 × 3 + 120s` `[D: آليات الاعتمادية]`.
- Warnings never change state: `diarization_failed`, `no_speech`, `chunk_failed:<idx>`, `low_snr` …
  `[D: آليات الاعتمادية؛ 1.5 تحليل الصوت]`.

## Edge cases
- `max_attempts = 1`: first transient error goes straight to FAILED(ATTEMPTS_EXHAUSTED).
- CANCEL_REQUESTED on a terminal job raises `InvalidTransitionError` (API maps it to 409 in S08).
- Backoff never exceeds cap, never negative, deterministic when `jitter=0`.

## Acceptance criteria
- **AC-1** `[D: الحالات]` — `test_jobs.py::test_allowed_transitions` (unit): every row of the table,
  parametrized, returns the expected `Transition`.
- **AC-2** `[D: الحالات]` — `test_jobs.py::test_forbidden_transitions` (unit): every (state, event) pair
  not in the table raises `InvalidTransitionError` (generated as the complement of the table).
- **AC-3** `[D: الحالات]` — `test_jobs.py::test_terminal_states_absorb` (unit).
- **AC-4** `[D: آليات الاعتمادية]` — `test_jobs.py::test_attempts_boundary` (unit): attempts = max−1, max, max+1.
- **AC-5** `[D: آليات الاعتمادية]` — `test_jobs_properties.py::test_backoff_bounds` (Hypothesis).
- **AC-6** `[D: آليات الاعتمادية]` — `test_jobs.py::test_timeout_formula` (unit): 1 h audio, RTF 0.02 → 336 s.
- **AC-7** — `test_jobs_properties.py::test_any_event_sequence_ends_valid` (Hypothesis): random event
  sequences either raise or keep the state inside `JobState`; no path leaves a terminal state.

## Commit plan
1. `docs(S02): add spec`
2. `test(S02): add acceptance tests (xfail)`
3. `feat(S02): add JobState, JobEvent, JobStage, ErrorCode`
4. `feat(S02): implement transition table`
5. `feat(S02): add backoff and processing timeout`
6. `docs(adr): 0006 stage hand-off between queues` (if not already merged)

## Open questions
- [ ] Q1 — The design diagram shows `RETRY_SCHEDULED → FAILED (attempts exhausted)`, the table does not.
  Proposed: decide exhaustion when the error happens (PROCESSING → FAILED) and drop that diagram
  edge; update the diagram in `docs/design.md` in this branch.
- [ ] Q2 — Backoff numbers are not in the design doc. Proposed defaults (config): base 30 s, cap 10 min, jitter 0.2.
- [ ] Q3 — `PROFILING` stage is not in the design's stage list ("المراحل داخل PROCESSING") but section 1.5
  adds the step. Proposed: add it after NORMALIZING and update the list in the design doc.
- [ ] Q4 — `PROCESSING → QUEUED` (hand-off from CPU to GPU queue) is not in the design table. See ADR-0006.
