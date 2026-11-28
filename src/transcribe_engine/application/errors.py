"""Application errors (S08). The presentation layer maps each to an HTTP status and problem+json.

Messages carry no tenant data, file names, or transcript text (CLAUDE.md logging rules).
"""

__all__ = [
    "AlignmentUnavailableError",
    "ApplicationError",
    "CorrectionsUnavailableError",
    "ForbiddenError",
    "IdempotencyKeyReusedError",
    "InvalidEditError",
    "InvalidWebhookUrlError",
    "JobAlreadyTerminalError",
    "JobNotFoundError",
    "QuotaExceededError",
    "ResultNotAvailableError",
    "ResultNotReadyError",
    "StaleVersionError",
    "TooManyActiveJobsError",
    "TranscriptNotFoundError",
    "UnauthorizedError",
    "UnsupportedFeatureError",
    "UnsupportedLanguageError",
    "UploadNotFoundError",
]


class ApplicationError(Exception):
    status: int = 500
    code: str = "internal"
    title: str = "Internal error"


class UnauthorizedError(ApplicationError):
    status = 401
    code = "unauthorized"
    title = "A valid API key is required"


class ForbiddenError(ApplicationError):
    status = 403
    code = "forbidden"
    title = "The API key lacks the required scope"


class UploadNotFoundError(ApplicationError):
    status = 404
    code = "upload_not_found"
    title = "Upload not found"


class JobNotFoundError(ApplicationError):
    status = 404
    code = "job_not_found"
    title = "Job not found"


class TranscriptNotFoundError(ApplicationError):
    status = 404
    code = "transcript_not_found"
    title = "Transcript not found"


class InvalidEditError(ApplicationError):
    status = 422
    code = "invalid_edit"
    title = "The edit names a segment or word that is not in this transcript"


class AlignmentUnavailableError(ApplicationError):
    """An edit needs new word times and no aligner is configured. Nothing is saved (S14, R-005)."""

    status = 503
    code = "alignment_unavailable"
    title = "Alignment is not available on this deployment yet"


class CorrectionsUnavailableError(ApplicationError):
    status = 503
    code = "corrections_unavailable"
    title = "Corrections are not configured on this deployment"


class StaleVersionError(ApplicationError):
    """The base version is no longer the latest; the editor must reload and re-apply (S22 AC-3)."""

    status = 409
    code = "stale_version"
    title = "The transcript changed since your base version"


class ResultNotAvailableError(ApplicationError):
    status = 404
    code = "result_not_available"
    title = "The result body is not available yet"


class JobAlreadyTerminalError(ApplicationError):
    status = 409
    code = "job_already_terminal"
    title = "The job has already finished"


class ResultNotReadyError(ApplicationError):
    status = 409
    code = "result_not_ready"
    title = "The job has not completed"


class UnsupportedLanguageError(ApplicationError):
    status = 422
    code = "unsupported_language"
    title = "Only explicit Arabic (ar) is supported"


class InvalidWebhookUrlError(ApplicationError):
    """Webhooks are https only (D-048). The destination is checked again at send time (S20)."""

    status = 422
    code = "invalid_webhook_url"
    title = "The webhook URL must be an https address"


class UnsupportedFeatureError(ApplicationError):
    status = 422
    code = "unsupported_feature"
    title = "This option is not available yet"


class TooManyActiveJobsError(ApplicationError):
    status = 429
    code = "too_many_active_jobs"
    title = "Too many jobs are active for this tenant"


class IdempotencyKeyReusedError(ApplicationError):
    status = 422
    code = "idempotency_key_reused"
    title = "This Idempotency-Key was used with a different request"


class QuotaExceededError(ApplicationError):
    status = 429
    code = "quota_exceeded"
    title = "The tenant's audio quota is used up"


class SearchUnavailableError(ApplicationError):
    """No embedder is configured on this deployment (S18, D-079)."""

    status = 503
    code = "search_unavailable"
