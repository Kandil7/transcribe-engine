"""Property tests for S02 — job state machine (specs/S02-job-state-machine.md)."""

import importlib
from datetime import timedelta
from types import ModuleType

import pytest
from hypothesis import given
from hypothesis import strategies as st


def _jobs() -> ModuleType:
    return importlib.import_module("transcribe_engine.domain.jobs")


@pytest.mark.xfail(strict=True, reason="S02")
@given(
    attempt=st.integers(min_value=1, max_value=60),
    base_ms=st.integers(min_value=1, max_value=86_400_000),
    cap_ms=st.integers(min_value=1, max_value=86_400_000 * 7),
    jitter=st.floats(min_value=0.0, max_value=1.0),
)
def test_backoff_bounds(attempt: int, base_ms: int, cap_ms: int, jitter: float) -> None:
    jobs = _jobs()
    base = timedelta(milliseconds=base_ms)
    cap = timedelta(milliseconds=cap_ms)
    delay = jobs.backoff(attempt, base=base, cap=cap, jitter=jitter)
    assert timedelta(0) <= delay <= cap


@given(
    events=st.lists(st.integers(min_value=0, max_value=10_000), max_size=40),
    attempts=st.integers(min_value=1, max_value=5),
)
def test_any_event_sequence_ends_valid(events: list[int], attempts: int) -> None:
    """Random event sequences either raise InvalidTransitionError (state unchanged) or move to a
    JobState; once a terminal state is reached, no event leaves it."""
    jobs = _jobs()
    event_values = list(jobs.JobEvent)
    state = jobs.JobState.PENDING_VALIDATION
    for raw in events:
        event = event_values[raw % len(event_values)]
        try:
            result = jobs.transition(
                state,
                event,
                attempt_count=attempts,
                max_attempts=3,
                error_code=jobs.ErrorCode.INTERNAL,
            )
        except jobs.InvalidTransitionError:
            continue
        assert not state.is_terminal, "a terminal state accepted an event"
        assert isinstance(result.to, jobs.JobState)
        state = result.to
