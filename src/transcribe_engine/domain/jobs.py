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
