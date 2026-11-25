"""Application errors (S08). The presentation layer maps each to an HTTP status and problem+json.

Messages carry no tenant data, file names, or transcript text (CLAUDE.md logging rules).
"""

__all__ = [
    "ApplicationError",
    "ForbiddenError",
    "JobAlreadyTerminalError",
    "JobNotFoundError",
    "QuotaExceededError",
    "ResultNotAvailableError",
    "ResultNotReadyError",
    "TooManyActiveJobsError",
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


class UnsupportedFeatureError(ApplicationError):
    status = 422
    code = "unsupported_feature"
    title = "This option is not available yet"


class TooManyActiveJobsError(ApplicationError):
    status = 429
    code = "too_many_active_jobs"
    title = "Too many jobs are active for this tenant"


class QuotaExceededError(ApplicationError):
    status = 429
    code = "quota_exceeded"
    title = "The tenant's audio quota is used up"
