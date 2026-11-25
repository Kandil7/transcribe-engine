"""Domain error taxonomy. Adapters translate library errors into these at the boundary.

The worker decides retry vs. fail only from the error class, never from library exception types.
"""


class DomainError(Exception):
    """Base class for all errors the domain and application layers understand."""

    code: str = "domain_error"


class TransientError(DomainError):
    """May succeed on retry (network blip, temporary OOM, timeout)."""

    code = "transient"


class PermanentError(DomainError):
    """Retrying cannot help (corrupt file, unsupported format, too long, bad config)."""

    code = "permanent"


class InvalidTransitionError(DomainError):
    """A job state change that the state machine does not allow."""

    code = "invalid_transition"


class LeaseLostError(DomainError):
    """The caller no longer owns the lease (expired, reclaimed or fenced out). Abort."""

    code = "lease_lost"


class JobCancelledError(DomainError):
    """The job was cancelled while it was being processed. Stop at the next checkpoint."""

    code = "job_cancelled"
