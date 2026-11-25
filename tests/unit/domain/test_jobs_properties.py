"""Property tests for S02 — job state machine (specs/S02-job-state-machine.md)."""

import importlib
from datetime import timedelta
from types import ModuleType

import pytest
from hypothesis import given
from hypothesis import strategies as st


def _jobs() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.jobs")


@given(
    attempt=st.integers(min_value=1, max_value=60),
    base_ms=st.integers(min_value=1, max_value=86_400_000),
    cap_ms=st.integers(min_value=1, max_value=86_400_000 * 7),
    jitter=st.floats(min_value=0.0, max_value=1.0),
)
def test_backoff_bounds(attempt: int, base_ms: int, cap_ms: int, jitter: float) -> None:
    """AC-5: 0 <= delay <= cap; delay follows min(cap, base * 2**(attempt-1)) +/- jitter."""
    jobs = _jobs()
    base = timedelta(milliseconds=base_ms)
    cap = timedelta(milliseconds=cap_ms)
    delay = jobs.backoff(attempt, base=base, cap=cap, jitter=jitter)
    raw_us = min(cap_ms * 1000, base_ms * 1000 * 2 ** (attempt - 1))
    lower = max(0, int(raw_us * (1 - jitter)) - 1)
    upper = min(cap_ms * 1000, int(raw_us * (1 + jitter)) + 1)
    assert timedelta(0) <= delay <= cap
    assert lower <= delay // timedelta(microseconds=1) <= upper


@given(
    events=st.lists(st.integers(min_value=0, max_value=10_000), max_size=40),
    attempts=st.integers(min_value=1, max_value=5),
)
def test_any_event_sequence_ends_valid(events: list[int], attempts: int) -> None:
    """AC-7: a rejected event leaves the state unchanged; an accepted event moves to a JobState.

    A terminal state rejects every event; CANCEL_REQUESTED on a non-terminal state ends CANCELLED.
    """
    jobs = _jobs()
    event_values = list(jobs.JobEvent)
    state = jobs.JobState.PENDING_VALIDATION
    for raw in events:
        event = event_values[raw % len(event_values)]
        if state.is_terminal:
            with pytest.raises(jobs.InvalidTransitionError):
                jobs.transition(
                    state,
                    event,
                    attempt_count=attempts,
                    max_attempts=3,
                    error_code=jobs.ErrorCode.INTERNAL,
                )
            continue
        try:
            result = jobs.transition(
                state,
                event,
                attempt_count=attempts,
                max_attempts=3,
                error_code=jobs.ErrorCode.INTERNAL,
            )
        except jobs.InvalidTransitionError:
            continue  # rejected: state stays exactly as it was
        assert isinstance(result.to, jobs.JobState)
        if event is jobs.JobEvent.CANCEL_REQUESTED:
            assert result.to is jobs.JobState.CANCELLED
        state = result.to
    assert isinstance(state, jobs.JobState)
