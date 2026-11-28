"""Acceptance tests for S02 — job state machine (specs/S02-job-state-machine.md).

The domain module is imported inside each test so that the file collects before it exists; the
xfail markers are removed in the commits that make each test pass.
"""

import importlib
from datetime import timedelta
from types import ModuleType

import pytest


def _jobs() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.jobs")


# Each row: state, event, attempt_count, max_attempts, error_code passed (or None), expected to,
# expected error_code. Rows are passed to a single parametrized argument.
ALLOWED = [
    ("PENDING_VALIDATION", "VALIDATED", 0, 3, None, "QUEUED", None),
    ("PENDING_VALIDATION", "CACHE_HIT", 0, 3, None, "COMPLETED", None),
    (
        "PENDING_VALIDATION",
        "VALIDATION_FAILED",
        0,
        3,
        "UNSUPPORTED_FORMAT",
        "FAILED",
        "UNSUPPORTED_FORMAT",
    ),
    ("QUEUED", "CLAIMED", 0, 3, None, "PROCESSING", None),
    ("PROCESSING", "SUCCEEDED", 1, 3, None, "COMPLETED", None),
    ("PROCESSING", "STAGE_HANDOFF", 1, 3, None, "QUEUED", None),
    ("PROCESSING", "TRANSIENT_ERROR", 1, 3, None, "RETRY_SCHEDULED", None),
    ("PROCESSING", "TRANSIENT_ERROR", 3, 3, None, "FAILED", "ATTEMPTS_EXHAUSTED"),
    ("PROCESSING", "PERMANENT_ERROR", 1, 3, "INVALID_MEDIA", "FAILED", "INVALID_MEDIA"),
    ("PROCESSING", "LEASE_EXPIRED", 1, 3, None, "RETRY_SCHEDULED", None),
    ("PROCESSING", "LEASE_EXPIRED", 3, 3, None, "FAILED", "POISON_JOB"),
    ("RETRY_SCHEDULED", "RETRY_DUE", 1, 3, None, "QUEUED", None),
    ("PENDING_VALIDATION", "CANCEL_REQUESTED", 0, 3, None, "CANCELLED", None),
    ("QUEUED", "CANCEL_REQUESTED", 0, 3, None, "CANCELLED", None),
    ("PROCESSING", "CANCEL_REQUESTED", 1, 3, None, "CANCELLED", None),
    ("RETRY_SCHEDULED", "CANCEL_REQUESTED", 1, 3, None, "CANCELLED", None),
]


@pytest.mark.parametrize("row", ALLOWED)
def test_allowed_transitions(row: tuple[str, str, int, int, str | None, str, str | None]) -> None:
    state, event, attempts, max_attempts, error_code, to, expected_code = row
    jobs = _jobs()
    kwargs = {"attempt_count": attempts, "max_attempts": max_attempts}
    if error_code is not None:
        kwargs["error_code"] = jobs.ErrorCode(error_code)
    result = jobs.transition(jobs.JobState(state), jobs.JobEvent(event), **kwargs)
    assert result.to == jobs.JobState(to)
    expected = None if expected_code is None else jobs.ErrorCode(expected_code)
    assert result.error_code == expected


def test_forbidden_transitions() -> None:
    """Every (state, event) pair not in the table raises InvalidTransitionError."""
    jobs = _jobs()
    allowed_pairs = {(row[0], row[1]) for row in ALLOWED}
    for state in jobs.JobState:
        for event in jobs.JobEvent:
            if (state.value, event.value) in allowed_pairs:
                continue
            if event == jobs.JobEvent.CANCEL_REQUESTED and not state.is_terminal:
                continue  # any non-terminal state cancels; covered by ALLOWED rows
            with pytest.raises(jobs.InvalidTransitionError):
                jobs.transition(
                    state,
                    event,
                    attempt_count=1,
                    max_attempts=3,
                    error_code=jobs.ErrorCode.INTERNAL,
                )


def test_terminal_states_absorb() -> None:
    jobs = _jobs()
    terminal = [s for s in jobs.JobState if s.is_terminal]
    assert {s.value for s in terminal} == {"COMPLETED", "FAILED", "CANCELLED"}
    for state in terminal:
        for event in jobs.JobEvent:
            with pytest.raises(jobs.InvalidTransitionError):
                jobs.transition(
                    state,
                    event,
                    attempt_count=1,
                    max_attempts=3,
                    error_code=jobs.ErrorCode.INTERNAL,
                )


# Rows: attempt_count, event, expected to, expected error code (max_attempts is 3).
ATTEMPT_ROWS = [
    (2, "TRANSIENT_ERROR", "RETRY_SCHEDULED", None),
    (3, "TRANSIENT_ERROR", "FAILED", "ATTEMPTS_EXHAUSTED"),
    (4, "TRANSIENT_ERROR", "FAILED", "ATTEMPTS_EXHAUSTED"),
    (2, "LEASE_EXPIRED", "RETRY_SCHEDULED", None),
    (3, "LEASE_EXPIRED", "FAILED", "POISON_JOB"),
    (4, "LEASE_EXPIRED", "FAILED", "POISON_JOB"),
]


@pytest.mark.parametrize(("attempts", "event", "to", "error_code"), ATTEMPT_ROWS)
def test_attempts_boundary(attempts: int, event: str, to: str, error_code: str | None) -> None:
    jobs = _jobs()
    result = jobs.transition(
        jobs.JobState.PROCESSING,
        jobs.JobEvent(event),
        attempt_count=attempts,
        max_attempts=3,
    )
    assert result.to == jobs.JobState(to)
    assert result.error_code == (None if error_code is None else jobs.ErrorCode(error_code))


def test_max_attempts_one_fails_on_first_lease_expiry() -> None:
    jobs = _jobs()
    result = jobs.transition(
        jobs.JobState.PROCESSING,
        jobs.JobEvent.LEASE_EXPIRED,
        attempt_count=1,
        max_attempts=1,
    )
    assert result.to == jobs.JobState.FAILED
    assert result.error_code == jobs.ErrorCode.POISON_JOB


def test_max_attempts_one_fails_on_first_transient_error() -> None:
    jobs = _jobs()
    result = jobs.transition(
        jobs.JobState.PROCESSING,
        jobs.JobEvent.TRANSIENT_ERROR,
        attempt_count=1,
        max_attempts=1,
    )
    assert result.to == jobs.JobState.FAILED
    assert result.error_code == jobs.ErrorCode.ATTEMPTS_EXHAUSTED


def test_warnings_are_strings_and_chunk_warning_is_formatted() -> None:
    """Warnings are plain codes; they never enter transition(), so they cannot change state."""
    jobs = _jobs()
    assert [w.value for w in jobs.Warning] == [
        "diarization_failed",
        "diarization_unavailable",  # D-084
        "speakers_above_limit",  # D-083
        "no_speech",
        "low_snr",
    ]
    assert jobs.chunk_failed_warning(3) == "chunk_failed:3"
    with pytest.raises(ValueError, match="non-negative"):
        jobs.chunk_failed_warning(-1)


def test_happy_path_reaches_completed() -> None:
    jobs = _jobs()
    state = jobs.JobState.PENDING_VALIDATION
    for event in ["VALIDATED", "CLAIMED", "SUCCEEDED"]:
        state = jobs.transition(state, jobs.JobEvent(event), attempt_count=1, max_attempts=3).to
    assert state == jobs.JobState.COMPLETED


def test_timeout_formula() -> None:
    """1 h audio at RTF_p95 0.02: 3600 s × 0.02 × 3 + 120 s = 336 s."""
    jobs = _jobs()
    assert jobs.processing_timeout(3_600_000, rtf_p95=0.02) == timedelta(seconds=336)


def test_timeout_accepts_explicit_factor_and_overhead() -> None:
    jobs = _jobs()
    assert jobs.processing_timeout(
        60_000, rtf_p95=0.5, factor=2.0, overhead=timedelta(seconds=10)
    ) == timedelta(seconds=70)


def test_backoff_is_exact_when_jitter_is_zero() -> None:
    jobs = _jobs()
    base, cap = timedelta(seconds=30), timedelta(minutes=10)
    assert jobs.backoff(1, base=base, cap=cap, jitter=0.0) == timedelta(seconds=30)
    assert jobs.backoff(2, base=base, cap=cap, jitter=0.0) == timedelta(seconds=60)
    assert jobs.backoff(3, base=base, cap=cap, jitter=0.0) == timedelta(seconds=120)
    assert jobs.backoff(30, base=base, cap=cap, jitter=0.0) == cap


def test_stage_order_is_the_pipeline_order() -> None:
    jobs = _jobs()
    assert [s.value for s in jobs.JobStage] == [
        "VALIDATING",
        "NORMALIZING",
        "PROFILING",
        "VAD",
        "ASR",
        "ALIGNING",
        "DIARIZING",
        "POSTPROCESSING",
        "PERSISTING",
    ]
