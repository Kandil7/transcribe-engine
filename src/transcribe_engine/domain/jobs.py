"""Job state machine: states, events, stages and error codes. Pure domain logic, no I/O.

Every job state change goes through `transition()`. Other layers must not
write a state directly.
"""

import random
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from transcribe_engine.domain.config import PipelineConfig
from transcribe_engine.domain.errors import InvalidTransitionError

__all__ = [
    "ErrorCode",
    "InvalidTransitionError",
    "Job",
    "JobEvent",
    "JobStage",
    "JobState",
    "Media",
    "Result",
    "Transition",
    "Warning",
    "backoff",
    "chunk_failed_warning",
    "processing_timeout",
    "transition",
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


class Warning(StrEnum):
    """Non-fatal conditions recorded on a job. Warnings never change state."""

    DIARIZATION_FAILED = "diarization_failed"
    NO_SPEECH = "no_speech"
    LOW_SNR = "low_snr"


def chunk_failed_warning(index: int) -> str:
    """Warning string for a failed chunk, e.g. `chunk_failed:3`."""
    if index < 0:
        raise ValueError("chunk index must be non-negative")
    return f"chunk_failed:{index}"


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


_MICROSECOND = timedelta(microseconds=1)
# Retry jitter is not security-sensitive (D-004); callers can inject `rng` for deterministic tests.
_JITTER_RNG = random.Random()  # noqa: S311 — retry jitter, not security; D-004
_MAX_EXPONENT = 62  # keeps 2**n far below any realistic cap; the cap clamps the result anyway


def backoff(
    attempt: int,
    *,
    base: timedelta,
    cap: timedelta,
    jitter: float,
    rng: random.Random | None = None,
) -> timedelta:
    """Exponential delay before retry `attempt` (1-based): min(cap, base * 2**(attempt-1)).

    `jitter` scales the delay by a uniform factor in [1 - jitter, 1 + jitter]; with jitter 0 the
    result is exact. The result is always within [0, cap].
    """
    if attempt < 1:
        raise ValueError("attempt is 1-based")
    if not 0.0 <= jitter <= 1.0:
        raise ValueError("jitter must be in [0, 1]")
    cap_us = cap // _MICROSECOND
    base_us = base // _MICROSECOND
    raw_us = min(cap_us, base_us * (1 << min(attempt - 1, _MAX_EXPONENT)))
    draw = rng if rng is not None else _JITTER_RNG
    factor = 1.0 + draw.uniform(-jitter, jitter) if jitter else 1.0
    return timedelta(microseconds=max(0, min(cap_us, int(raw_us * factor))))


def processing_timeout(
    duration_ms: int,
    *,
    rtf_p95: float,
    factor: float = 3.0,
    overhead: timedelta = timedelta(seconds=120),
) -> timedelta:
    """Time budget for one processing attempt: duration × RTF_p95 × factor + overhead."""
    return timedelta(milliseconds=duration_ms * rtf_p95 * factor) + overhead


@dataclass(frozen=True)
class Media:
    """One distinct input file, identified by its content hash (S05)."""

    id: str
    sha256: str
    storage_key: str
    duration_ms: int
    format: str
    size_bytes: int


@dataclass(frozen=True)
class Job:
    """One request to process a media file under one tenant and one pipeline configuration."""

    id: str
    tenant_id: str
    media_id: str
    state: JobState
    stage: JobStage | None
    attempt_count: int
    max_attempts: int
    queue: str  # "cpu" or "gpu" (ADR-0006)
    config: PipelineConfig
    result_id: str | None
    error_code: ErrorCode | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    """A processed output shared by every job with the same result key (D-007)."""

    id: str
    result_key: str
    media_id: str
    config: PipelineConfig
    ref_count: int
