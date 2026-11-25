"""Job state machine: states, events, stages and error codes. Pure domain logic, no I/O.

Every job state change goes through `transition()` (added in the next step). Other layers must not
write a state directly.
"""

from dataclasses import dataclass
from enum import StrEnum

from transcribe_engine.domain.errors import InvalidTransitionError

__all__ = [
    "ErrorCode",
    "InvalidTransitionError",
    "JobEvent",
    "JobStage",
    "JobState",
    "Transition",
]


class JobState(StrEnum):
    PENDING_VALIDATION = "PENDING_VALIDATION"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED})


class JobStage(StrEnum):
    """Pipeline stages, in order. Stage names are used in logs and in the `stage` column."""

    VALIDATING = "VALIDATING"
    NORMALIZING = "NORMALIZING"
    PROFILING = "PROFILING"
    VAD = "VAD"
    ASR = "ASR"
    ALIGNING = "ALIGNING"
    DIARIZING = "DIARIZING"
    POSTPROCESSING = "POSTPROCESSING"
    PERSISTING = "PERSISTING"


class JobEvent(StrEnum):
    VALIDATED = "VALIDATED"
    CACHE_HIT = "CACHE_HIT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CLAIMED = "CLAIMED"
    STAGE_HANDOFF = "STAGE_HANDOFF"
    SUCCEEDED = "SUCCEEDED"
    TRANSIENT_ERROR = "TRANSIENT_ERROR"
    PERMANENT_ERROR = "PERMANENT_ERROR"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    RETRY_DUE = "RETRY_DUE"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"


class ErrorCode(StrEnum):
    INVALID_MEDIA = "INVALID_MEDIA"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    TOO_LONG = "TOO_LONG"
    TOO_LARGE = "TOO_LARGE"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    ATTEMPTS_EXHAUSTED = "ATTEMPTS_EXHAUSTED"
    POISON_JOB = "POISON_JOB"
    TIMEOUT = "TIMEOUT"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True)
class Transition:
    to: JobState
    error_code: ErrorCode | None = None


_SIMPLE: dict[tuple[JobState, JobEvent], JobState] = {
    (JobState.PENDING_VALIDATION, JobEvent.VALIDATED): JobState.QUEUED,
    (JobState.PENDING_VALIDATION, JobEvent.CACHE_HIT): JobState.COMPLETED,
    (JobState.QUEUED, JobEvent.CLAIMED): JobState.PROCESSING,
    (JobState.PROCESSING, JobEvent.SUCCEEDED): JobState.COMPLETED,
    (JobState.PROCESSING, JobEvent.STAGE_HANDOFF): JobState.QUEUED,
    (JobState.RETRY_SCHEDULED, JobEvent.RETRY_DUE): JobState.QUEUED,
}

# Failure events that always end in FAILED; the caller supplies the error code.
_FAILS_WITH_CALLER_CODE = {
    (JobState.PENDING_VALIDATION, JobEvent.VALIDATION_FAILED),
    (JobState.PROCESSING, JobEvent.PERMANENT_ERROR),
}

# Failure events that retry while attempts remain, then fail with their own code.
_RETRYABLE: dict[JobEvent, ErrorCode] = {
    JobEvent.TRANSIENT_ERROR: ErrorCode.ATTEMPTS_EXHAUSTED,
    JobEvent.LEASE_EXPIRED: ErrorCode.POISON_JOB,
}


def transition(
    state: JobState,
    event: JobEvent,
    *,
    attempt_count: int,
    max_attempts: int,
    error_code: ErrorCode | None = None,
) -> Transition:
    """Return the next state for `event`, or raise InvalidTransitionError if the table forbids it.

    `attempt_count` counts claims, including the current one (incremented at claim time).
    `error_code` is required for VALIDATION_FAILED and PERMANENT_ERROR and ignored otherwise.
    """
    if state.is_terminal:
        raise InvalidTransitionError(f"{state} is terminal; {event} is not allowed")
    if event is JobEvent.CANCEL_REQUESTED:
        return Transition(to=JobState.CANCELLED)
    key = (state, event)
    if key in _SIMPLE:
        return Transition(to=_SIMPLE[key])
    if key in _FAILS_WITH_CALLER_CODE:
        if error_code is None:
            raise ValueError(f"{event} requires an error_code")
        return Transition(to=JobState.FAILED, error_code=error_code)
    if state is JobState.PROCESSING and event in _RETRYABLE:
        if attempt_count < max_attempts:
            return Transition(to=JobState.RETRY_SCHEDULED)
        return Transition(to=JobState.FAILED, error_code=_RETRYABLE[event])
    raise InvalidTransitionError(f"{event} is not allowed in {state}")
