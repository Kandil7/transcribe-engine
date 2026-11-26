"""RFC 9457 problem+json for application errors (S08).

Only code and title reach the client, never the exception message (it may hold internal detail).
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from transcribe_engine.application.errors import ApplicationError

PROBLEM_BASE = "https://errors.transcribe-engine.local/"
PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem(error: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={
            "type": PROBLEM_BASE + error.code,
            "title": error.title,
            "status": error.status,
            "code": error.code,
        },
        media_type=PROBLEM_MEDIA_TYPE,
    )


def install_error_handlers(app: FastAPI) -> None:
    async def _handle(_: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, ApplicationError):
            raise exc
        return problem(exc)

    app.add_exception_handler(ApplicationError, _handle)

    async def _invalid(_: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, RequestValidationError):
            raise exc
        return JSONResponse(
            status_code=422,
            content={
                "type": PROBLEM_BASE + "invalid_request",
                "title": "The request is not valid",
                "status": 422,
                "code": "invalid_request",
                "errors": [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()],
            },
            media_type=PROBLEM_MEDIA_TYPE,
        )

    app.add_exception_handler(RequestValidationError, _invalid)
