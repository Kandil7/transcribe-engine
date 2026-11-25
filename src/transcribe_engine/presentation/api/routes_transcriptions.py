"""POST /v1/transcriptions: create a job from an upload (S08). 202 Accepted with Location."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.application.use_cases.create_job import (
    CreateJobCommand,
    CreateTranscriptionJob,
)
from transcribe_engine.presentation.api.deps import require_scope
from transcribe_engine.presentation.api.schemas import CreateTranscriptionIn

router = APIRouter()


@router.post("/v1/transcriptions", status_code=202)
async def create_transcription(
    request: Request,
    body: CreateTranscriptionIn,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:write"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=255)] = None,
) -> JSONResponse:
    use_case = CreateTranscriptionJob(request.app.state.make_uow, request.app.state.storage)
    result = await use_case(
        CreateJobCommand(
            tenant_id=principal.tenant_id,
            upload_id=body.upload_id,
            language=body.language,
            engine=body.engine,
            diarization=body.diarization,
            webhook_url=body.webhook_url,
            idempotency_key=idempotency_key,
        )
    )
    return JSONResponse(
        status_code=result.status,
        content=result.body,
        headers={"Location": f"/v1/transcriptions/{result.job_id}"},
    )
