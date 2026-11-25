"""Job endpoints (S08): read, cancel, request deletion, and the result body (json only for now)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from transcribe_engine.application.errors import UnsupportedFeatureError
from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.application.use_cases.cancel_job import CancelJob
from transcribe_engine.application.use_cases.job_queries import GetJob, GetResult
from transcribe_engine.application.use_cases.request_deletion import RequestDeletion
from transcribe_engine.domain.jobs import Job
from transcribe_engine.presentation.api.deps import require_scope
from transcribe_engine.presentation.api.schemas import DeletionOut, JobOut

router = APIRouter()
RETRY_AFTER_SECONDS = "5"  # while a job is not terminal, clients poll no faster than this


def _job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        state=job.state.value,
        stage=job.stage.value if job.stage else None,
        progress=job.progress,
        warnings=list(job.warnings),
        error_code=job.error_code.value if job.error_code else None,
    )


@router.get("/v1/transcriptions/{job_id}", response_model=JobOut)
async def get_transcription(
    request: Request,
    job_id: str,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:read"))],
) -> JSONResponse:
    job = await GetJob(request.app.state.make_uow)(principal.tenant_id, job_id)
    headers = {} if job.state.is_terminal else {"Retry-After": RETRY_AFTER_SECONDS}
    return JSONResponse(content=_job_out(job).model_dump(), headers=headers)


@router.post("/v1/transcriptions/{job_id}:cancel", status_code=202, response_model=JobOut)
async def cancel_transcription(
    request: Request,
    job_id: str,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:write"))],
) -> JSONResponse:
    job = await CancelJob(request.app.state.make_uow)(principal.tenant_id, job_id)
    return JSONResponse(status_code=202, content=_job_out(job).model_dump())


@router.delete("/v1/transcriptions/{job_id}", status_code=202, response_model=DeletionOut)
async def request_transcription_deletion(
    request: Request,
    job_id: str,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:write"))],
) -> JSONResponse:
    at = await RequestDeletion(request.app.state.make_uow)(principal.tenant_id, job_id)
    body = DeletionOut(id=job_id, deletion_requested_at=at)
    return JSONResponse(status_code=202, content=body.model_dump(mode="json"))


@router.get("/v1/transcriptions/{job_id}/result", response_model=None)
async def get_transcription_result(
    request: Request,
    job_id: str,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:read"))],
    format: Annotated[str, Query()] = "json",
) -> Response:
    if format != "json":
        raise UnsupportedFeatureError
    await GetResult(request.app.state.make_uow)(principal.tenant_id, job_id)
    return Response(status_code=204)  # unreachable until S10 writes transcript versions
